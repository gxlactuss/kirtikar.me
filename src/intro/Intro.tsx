import { useEffect, useRef, useState, type ReactNode } from 'react';

import { forceFixtures } from '../machine/flags';
import { useDemo } from '../machine/store';
import { createAtomiser, type Atomiser } from './atomiser';
import { MARK_PIECES, MARK_VIEWBOX, WORD_FILL, WORD_PATH, WORD_VIEWBOX } from './mark';
import css from './intro.module.css';

/**
 * The opening sequence: logo, then the quick guide, then the demo itself.
 *
 * Three acts share one sticky pane and are cross-faded by scroll position,
 * so the whole thing is a single page that the wheel plays through rather
 * than a slideshow with its own timer. Nothing here is on a clock: a visitor
 * who scrolls fast sees it fast.
 *
 * It also buys the backend its warm-up. The stage — and with it the health
 * watcher in BackendChip — is mounted from the first frame, invisible behind
 * the intro, so a Space that needs ninety seconds to wake has been waking
 * the entire time the visitor was reading. That is the point of the act two
 * status line: it is the real check, not a decoration.
 *
 * Everything below the React render is written imperatively against refs in
 * one animation frame. Re-rendering seven petals and four thousand particles
 * through React on every scroll event would drop frames, and a stuttering
 * opening is worse than no opening.
 */

/** How far the page scrolls, as a multiple of the viewport. Set inline on
 * the track rather than in the stylesheet so the one number that decides the
 * pace of the whole sequence sits beside the windows it is divided into. */
const TRACK_VH = 420;

/** Scroll-progress windows, in [0, 1] over the whole track. */
const HERO_OUT: Span = [0.02, 0.3];
const HERO_GONE: Span = [0.26, 0.33];
const GUIDE_IN: Span = [0.28, 0.42];
const GUIDE_OUT: Span = [0.66, 0.78];
const PANE_OUT: Span = [0.76, 0.9];
const VEIL: Span = [0.74, 0.94];
const STAGE_IN: Span = [0.83, 1];

type Span = readonly [number, number];

/** Per-petal flight: offset in viewBox units, spin in degrees, and how long
 * the piece holds on before it lets go. The base sweep sinks, the leaves
 * fan outward, and the centre petal is the last thing to leave.
 *
 * The offsets are large on purpose — a couple of mark-widths each. Anything
 * smaller and the petals visibly dissolve where they stand instead of
 * leaving the frame, which is the difference between a logo fading out and
 * a flower coming apart in the wind. The sticky pane clips them. */
interface Drift {
  dx: number;
  dy: number;
  rot: number;
  /** Fraction of act one this piece waits before it lets go. */
  hold: number;
  /** Travel easing exponent. Above 1 the piece hangs, then accelerates. */
  ease?: number;
  /** Multiplies how fast it gives out. Above 1 fades early. */
  fade?: number;
}

const DRIFT: Record<string, Drift> = {
  // The base sweep is the only piece whose path crosses the wordmark, so it
  // leaves early and thins out fast rather than sinking through the letters
  // at full strength while they are still dissolving.
  base: { dx: 0, dy: 2600, rot: -10, hold: 0, ease: 1.15, fade: 1.7 },
  leafL: { dx: -2300, dy: -820, rot: -150, hold: 0.06 },
  leafR: { dx: 2300, dy: -820, rot: 150, hold: 0.06 },
  petalL: { dx: -1650, dy: -1500, rot: -130, hold: 0.16 },
  petalR: { dx: 1650, dy: -1500, rot: 130, hold: 0.16 },
  centre: { dx: 140, dy: -2100, rot: 34, hold: 0.26 },
  seed: { dx: -110, dy: -2500, rot: 0, hold: 0.34 },
};

const GUIDE = [
  {
    title: 'Pick one photo',
    body: (
      <>
        Pick one of the <em>ten craft photos</em>, or upload a photo of your own.
        One is all it needs.
      </>
    ),
  },
  {
    title: 'Say one sentence',
    body: (
      <>
        Hold the button and describe it — what it is, what it is made of, how long it
        took. <em>Up to 30 seconds</em>, in any language you like.
      </>
    ),
  },
  {
    title: 'Watch it write the listing',
    body: (
      <>
        The background is cut out, your voice is transcribed and translated, and the
        title, description, fact sheet and <em>price band</em> are written from both.
      </>
    ),
  },
];

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const span = (p: number, [a, b]: Span) => clamp01((p - a) / (b - a));
const easeOut = (t: number) => 1 - (1 - t) ** 3;
const easeInOut = (t: number) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2);

const SEEN_KEY = 'kirtikar:intro-seen';

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

/**
 * The backend's real state, shown while the visitor reads the guide.
 *
 * A forced-fixtures build never calls the backend at all — BackendChip does
 * not even start the health watcher — so `backend` would sit on `unknown`
 * forever and this line would claim to be checking something it is not.
 * Say what that build actually does instead.
 */
function WarmingLine() {
  const { backend } = useDemo();

  if (forceFixtures()) {
    return (
      <p className={css.footnote}>
        <span className={css.warmDot} data-live="1" />
        This build replays a recorded run of the pipeline, so nothing here waits on
        a server.
      </p>
    );
  }

  const text = {
    unknown: 'Checking the server…',
    warming: 'Waking the server — it sleeps when nobody is using it.',
    live: 'The server is awake and answering.',
    down: 'The server is not answering; the demo will replay a recorded run.',
  }[backend];

  return (
    <p className={css.footnote}>
      <span
        className={css.warmDot}
        data-live={backend === 'live' ? '1' : backend === 'down' ? 'down' : '0'}
      />
      {text}
    </p>
  );
}

export function Intro({ children }: { children: ReactNode }) {
  // Landing is one-way on purpose. A judge who is part-way through recording
  // should not be able to scroll themselves back out of the demo by accident.
  const [landed, setLanded] = useState(
    () => prefersReducedMotion() || sessionStorage.getItem(SEEN_KEY) === '1',
  );

  // Bumped by replay, which tears the whole sequence down and builds it
  // again rather than trying to rewind the state it left behind.
  const [runId, setRunId] = useState(0);

  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const landedRef = useRef(landed);
  landedRef.current = landed;

  // --- the animation ----------------------------------------------------
  useEffect(() => {
    const host = hostRef.current;
    const cnv = canvasRef.current;
    if (!host || !cnv) return;
    const canvas = cnv;

    const q = <T extends Element>(sel: string) => host.querySelector<T>(sel);
    const track = q<HTMLElement>(`.${css.track}`)!;
    const pane = q<HTMLElement>(`.${css.pane}`)!;
    const veil = q<HTMLElement>(`.${css.veil}`)!;
    const hero = q<HTMLElement>(`.${css.hero}`)!;
    const tagline = q<HTMLElement>(`.${css.tagline}`)!;
    const cue = q<HTMLElement>(`.${css.cue}`)!;
    const word = q<HTMLElement>(`.${css.word}`)!;
    const wordSvg = q<SVGElement>(`.${css.wordSvg}`)!;
    const guide = q<HTMLElement>(`.${css.actGuide}`)!;
    const stageWrap = q<HTMLElement>(`.${css.stageWrap}`)!;
    const skip = q<HTMLElement>(`.${css.skip}`);
    const pieces = [...host.querySelectorAll<SVGPathElement>('[data-piece]')];
    const cards = [...host.querySelectorAll<HTMLElement>('[data-card]')];

    const atomiser: Atomiser = createAtomiser(
      canvas,
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${WORD_VIEWBOX.w} ${WORD_VIEWBOX.h}">` +
        `<path fill="${WORD_FILL}" fill-rule="evenodd" d="${WORD_PATH}"/></svg>`,
    );

    const sizeCanvas = () => {
      const r = word.getBoundingClientRect();
      if (r.width > 0) atomiser.layout(r.width, (r.width * WORD_VIEWBOX.h) / WORD_VIEWBOX.w);
    };
    const ro = new ResizeObserver(sizeCanvas);
    ro.observe(word);

    // The petals fly *in* from half-dispersed on first paint, along the same
    // paths they will later fly out on. Reusing the drift means the entrance
    // and the exit are visibly the same motion run in opposite directions.
    const ENTRANCE_MS = 1150;
    const start = performance.now();
    let entranceDone = landedRef.current;

    let target = 0;
    let cur = 0;
    let raf = 0;
    let running = false;

    const maxScroll = () => Math.max(1, track.offsetHeight - window.innerHeight);

    function apply(p: number, entrance: number) {
      const vh = window.innerHeight;

      // --- act one: the logo comes apart ---
      const out = span(p, HERO_OUT);
      // Only a nudge: a larger drift here would cancel the base sweep's sink
      // and leave the whole mark looking pinned.
      hero.style.transform = `translate3d(0, ${-out * vh * 0.03}px, 0) scale(${1 + out * 0.08})`;
      hero.style.opacity = String(1 - span(p, HERO_GONE));

      for (const el of pieces) {
        const d = DRIFT[el.dataset.piece!];
        if (!d) continue;
        // `entrance` is a dispersal amount too, so max() lets whichever of
        // the two is further along own the petal.
        const local = Math.max(clamp01((out - d.hold) / (1 - d.hold)), entrance);
        const e = local ** (d.ease ?? 1.7);
        const sway = Math.sin(local * Math.PI * 2.4 + d.hold * 9) * 120 * local;
        el.style.transform =
          `translate(${d.dx * e + sway}px, ${d.dy * e}px) ` +
          `rotate(${d.rot * e}deg) scale(${1 - 0.3 * e})`;
        // Holds full colour for the first half of the flight and only then
        // gives out, so the petal is seen leaving rather than dimming.
        el.style.opacity = String(clamp01(((1 - local) * 1.9) / (d.fade ?? 1)));
      }

      // The word dissolves a beat after the petals start moving.
      const wordOut = span(p, [HERO_OUT[0] + 0.03, HERO_OUT[1] - 0.02]);
      if (atomiser.isReady()) {
        atomiser.draw(wordOut);
        canvas.dataset.live = '1';
        wordSvg.dataset.hidden = '1';
      }
      word.style.transform = `translate3d(0, ${entrance * 26}px, 0)`;
      word.style.opacity = String(
        (1 - entrance) * (atomiser.isReady() ? 1 : 1 - easeOut(wordOut)),
      );

      const taglineOut = span(p, [0.005, 0.09]);
      tagline.style.opacity = String((1 - taglineOut) * (1 - entrance));
      tagline.style.transform = `translate3d(0, ${taglineOut * -14 + entrance * 20}px, 0)`;
      cue.style.opacity = String((1 - span(p, [0, 0.05])) * (1 - entrance));

      // --- act two: the guide ---
      const gIn = span(p, GUIDE_IN);
      const gOut = span(p, GUIDE_OUT);
      guide.style.opacity = String(gIn * (1 - gOut));
      guide.style.transform = `translate3d(0, ${(1 - easeOut(gIn)) * 44 - gOut * 60}px, 0)`;
      cards.forEach((card, i) => {
        const t = span(p, [GUIDE_IN[0] + 0.02 + i * 0.035, GUIDE_IN[1] + 0.02 + i * 0.035]);
        card.style.opacity = String(t);
        card.style.transform = `translate3d(0, ${(1 - easeOut(t)) * 40}px, 0)`;
      });

      // --- act three: the stage arrives ---
      veil.style.opacity = String(easeInOut(span(p, VEIL)));
      const paneOut = span(p, PANE_OUT);
      pane.style.opacity = String(1 - paneOut);
      // The skip control belongs to the cream world; it must not be left
      // sitting on the black stage while the handoff is still running.
      if (skip) {
        skip.style.opacity = String(1 - paneOut);
        skip.style.pointerEvents = paneOut > 0.5 ? 'none' : 'auto';
      }
      const sIn = easeOut(span(p, STAGE_IN));
      stageWrap.style.opacity = String(sIn);
      stageWrap.style.transform = `scale(${0.94 + 0.06 * sIn})`;
    }

    function frame(now: number) {
      const entrance = entranceDone
        ? 0
        : (1 - easeOut(clamp01((now - start) / ENTRANCE_MS))) * 0.6;
      if (entrance === 0) entranceDone = true;

      // Chasing the scroll rather than tracking it exactly is what turns a
      // notched trackpad or a coarse wheel into continuous motion.
      cur += (target - cur) * 0.13;
      if (Math.abs(target - cur) < 0.0004) cur = target;

      apply(cur, entrance);

      if (target >= 0.999 && !landedRef.current) {
        sessionStorage.setItem(SEEN_KEY, '1');
        setLanded(true);
      }

      if (cur !== target || !entranceDone) {
        raf = requestAnimationFrame(frame);
      } else {
        running = false;
      }
    }

    function kick() {
      if (running || landedRef.current) return;
      running = true;
      raf = requestAnimationFrame(frame);
    }

    function onScroll() {
      target = clamp01(window.scrollY / maxScroll());
      kick();
    }

    // Atomiser readiness arrives asynchronously; redraw once it does.
    const readyPoll = window.setInterval(() => {
      if (atomiser.isReady()) {
        window.clearInterval(readyPoll);
        kick();
        apply(cur, 0);
      }
    }, 80);

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    onScroll();
    kick();

    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      window.clearInterval(readyPoll);
      cancelAnimationFrame(raf);
      ro.disconnect();
      atomiser.destroy();
    };
  }, [runId]);

  // --- page scrolling is only on while the intro is ----------------------
  useEffect(() => {
    document.documentElement.classList.toggle('introRunning', !landed);
    if (landed) return;
    return () => document.documentElement.classList.remove('introRunning');
  }, [landed]);

  // Escape skips; it is the one key a visitor tries when a page takes over.
  useEffect(() => {
    if (landed) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') skip();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [landed]);

  function skip() {
    const track = hostRef.current?.querySelector<HTMLElement>(`.${css.track}`);
    if (!track) return;
    // Scrolled, not jumped: the sequence plays through at speed rather than
    // cutting, so a visitor who skips still sees where they ended up.
    window.scrollTo({ top: track.offsetHeight - window.innerHeight, behavior: 'smooth' });
  }

  function replay() {
    sessionStorage.removeItem(SEEN_KEY);
    window.scrollTo({ top: 0, behavior: 'auto' });
    setLanded(false);
    setRunId((n) => n + 1);
  }

  return (
    <div className={css.intro} ref={hostRef}>
      <div className={css.backdrop} aria-hidden="true" />
      <div className={css.veil} aria-hidden="true" />

      <div
        className={css.track}
        style={{ height: `${TRACK_VH}svh` }}
        data-landed={landed ? '1' : '0'}
        aria-hidden={landed}
      >
        <div className={css.pane}>
          {/* --- act one --- */}
          <section className={`${css.act} ${css.actHero}`}>
            <div className={css.hero}>
              <svg
                className={css.mark}
                viewBox={`0 0 ${MARK_VIEWBOX.w} ${MARK_VIEWBOX.h}`}
                role="img"
                aria-label="Kirtikar"
              >
                {MARK_PIECES.map((piece) => (
                  <path
                    key={piece.id}
                    className={css.piece}
                    data-piece={piece.id}
                    style={{ transformOrigin: `${piece.cx}px ${piece.cy}px` }}
                    fill={piece.fill}
                    fillRule="evenodd"
                    d={piece.d}
                  />
                ))}
              </svg>

              <div className={css.word}>
                <svg
                  className={css.wordSvg}
                  viewBox={`0 0 ${WORD_VIEWBOX.w} ${WORD_VIEWBOX.h}`}
                  aria-hidden="true"
                >
                  <path fill={WORD_FILL} fillRule="evenodd" d={WORD_PATH} />
                </svg>
                <canvas className={css.wordCanvas} ref={canvasRef} aria-hidden="true" />
              </div>

              <p className={css.tagline}>One photo. One sentence. A finished listing.</p>
            </div>

            <div className={css.cue} aria-hidden="true">
              <span>Scroll</span>
              <span className={css.cueLine} />
            </div>
          </section>

          {/* --- act two --- */}
          <section className={`${css.act} ${css.actGuide}`}>
            <p className={css.eyebrow}>How to use it</p>
            <h2 className={css.guideTitle}>Three things to do. About a minute.</h2>
            <ol className={css.cards}>
              {GUIDE.map((step, i) => (
                <li className={css.card} data-card key={step.title}>
                  <span className={css.step}>{i + 1}</span>
                  <h3 className={css.cardTitle}>{step.title}</h3>
                  <p className={css.cardBody}>{step.body}</p>
                </li>
              ))}
            </ol>
            <WarmingLine />
          </section>
        </div>
      </div>

      <div className={css.stageWrap} data-landed={landed ? '1' : '0'}>
        {children}
      </div>

      {landed ? (
        <button className={css.replay} onClick={replay}>
          Replay intro
        </button>
      ) : (
        <button className={css.skip} onClick={skip}>
          Skip to the demo
        </button>
      )}
    </div>
  );
}
