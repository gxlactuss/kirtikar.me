/**
 * Dissolves the "Kirtikar" wordmark into drifting particles.
 *
 * The wordmark is rasterised once from the traced vector at the exact size
 * and device pixel ratio it will be shown at, then sampled on a grid: every
 * opaque cell becomes one particle that remembers where it came from. At
 * rest the canvas simply draws the raster, so the opening frame is the
 * artwork itself rather than an approximation of it — the particles only
 * take over once the visitor starts scrolling, by which point nobody can
 * tell a 3px square from a letter stem.
 *
 * Deliberately not React: this redraws on every animation frame while the
 * page is being scrolled, and a component that re-rendered four thousand
 * particles per frame would make the rest of the page stutter.
 */

/** Grid pitch, in device pixels. Smaller is finer and slower. */
const STEP = 4;

/**
 * Rasterise at no less than 2x whatever the screen reports.
 *
 * Particle size is a fixed number of *device* pixels, so on a 1x display a
 * STEP-sized square is twice as coarse as on a retina one and the dissolve
 * reads as speckle rather than dust. Oversampling costs one more raster and
 * makes the grain identical everywhere.
 */
const MIN_DPR = 2;

/** Alpha below this is treated as background rather than ink. */
const INK_ALPHA = 110;

/**
 * Headroom around the wordmark, as multiples of its own width and height.
 *
 * Without it the canvas is exactly the size of the word, and every particle
 * that leaves that box is clipped against its edge — which reads as a hard
 * horizontal line the dust vanishes along, the one thing that gives the
 * whole effect away. The canvas is grown instead and hung off the word by
 * the same amounts, so the art still lines up with the vector underneath.
 *
 * `FADE` then dissolves whatever is still alive before it reaches the new
 * edge, so the boundary is never the thing that ends a particle.
 */
const PAD = { x: 0.34, top: 3.2, bottom: 0.45 };

/** Fraction of the padding used to fade particles out near the edge. */
const FADE = { top: 0.62, side: 0.75 };

export interface Atomiser {
  /** Size (and re-sample) for a new CSS box. Safe to call repeatedly. */
  layout(cssWidth: number, cssHeight: number): void;
  /** Paint the wordmark dissolved by `t`, where 0 is intact and 1 is gone. */
  draw(t: number): void;
  /** True once the raster has decoded and particles exist. */
  isReady(): boolean;
  destroy(): void;
}

/** The wordmark's own box inside the padded canvas, in device pixels. */
interface Ink {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Particles {
  /** Rest position, in device pixels. */
  x: Float32Array;
  y: Float32Array;
  /** Unit drift direction. */
  dx: Float32Array;
  dy: Float32Array;
  /** Travel distance at full dispersal, in device pixels. */
  reach: Float32Array;
  /** Fraction of the timeline this particle waits before it lets go. */
  delay: Float32Array;
  /** Phase offset for the per-particle sway. */
  phase: Float32Array;
  n: number;
}

/**
 * Cheap smooth noise in [0, 1]. Two out-of-phase sine products give soft
 * organic patches, which is all this needs — the alternative is shipping a
 * Perlin implementation to decide when a 3px square starts moving.
 */
function patches(x: number, y: number): number {
  const a = Math.sin(x * 0.013 + y * 0.021);
  const b = Math.sin(x * 0.0051 - y * 0.0094 + 2.1);
  return (a * b + 1) / 2;
}

function sample(data: Uint8ClampedArray, w: number, ink: Ink): Particles {
  const xs: number[] = [];
  const ys: number[] = [];

  // Only the ink box is walked: the rest of the padded canvas is empty by
  // construction, and scanning it would be pure cost.
  const yEnd = ink.y + ink.h;
  const xEnd = ink.x + ink.w;
  for (let y = ink.y; y < yEnd; y += STEP) {
    for (let x = ink.x; x < xEnd; x += STEP) {
      if (data[(y * w + x) * 4 + 3]! >= INK_ALPHA) {
        xs.push(x);
        ys.push(y);
      }
    }
  }

  const n = xs.length;
  const p: Particles = {
    x: new Float32Array(n),
    y: new Float32Array(n),
    dx: new Float32Array(n),
    dy: new Float32Array(n),
    reach: new Float32Array(n),
    delay: new Float32Array(n),
    phase: new Float32Array(n),
    n,
  };

  // Ordered by delay so the draw loop walks particles of similar opacity
  // together and can change globalAlpha a few dozen times instead of n times.
  const order = new Array<number>(n);
  const delays = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    order[i] = i;
    // Reads left to right, the way the word does, roughened by the noise so
    // the edge of the dissolve is a frayed front rather than a wipe.
    delays[i] = 0.3 * ((xs[i]! - ink.x) / ink.w) + 0.24 * patches(xs[i]!, ys[i]!);
  }
  order.sort((a, b) => delays[a]! - delays[b]!);

  for (let k = 0; k < n; k++) {
    const i = order[k]!;
    const x = xs[i]!;
    const y = ys[i]!;
    // Mostly upward, fanned outward from the centre of the word: ink from
    // the K blows left, ink from the r blows right.
    const spread = ((x - ink.x) / ink.w - 0.5) * 1.25;
    const ang = -Math.PI / 2 + spread + (Math.random() - 0.5) * 1.5;
    p.x[k] = x;
    p.y[k] = y;
    p.dx[k] = Math.cos(ang);
    p.dy[k] = Math.sin(ang);
    p.reach[k] = ink.h * (1.2 + Math.random() * 2.2);
    p.delay[k] = delays[i]!;
    p.phase[k] = Math.random() * Math.PI * 2;
  }
  return p;
}

export function createAtomiser(canvas: HTMLCanvasElement, svg: string): Atomiser {
  const ctx = canvas.getContext('2d');
  const image = new Image();
  let particles: Particles | null = null;
  let ink: Ink | null = null;
  let want: { w: number; h: number; dpr: number } | null = null;
  let have: { w: number; h: number; dpr: number } | null = null;
  let dead = false;
  let decoding = false;

  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;

  const build = async () => {
    if (dead || decoding || !ctx || !want) return;
    if (have && have.w === want.w && have.h === want.h && have.dpr === want.dpr) return;

    decoding = true;
    const size = want;
    try {
      await image.decode();
    } catch {
      decoding = false;
      return; // The inline <svg> underneath stays visible; nothing breaks.
    }
    decoding = false;
    if (dead) return;

    // The ink box is the word at its real size; the canvas is that box plus
    // the headroom the dust flies into.
    const iw = Math.max(1, Math.round(size.w * size.dpr));
    const ih = Math.max(1, Math.round(size.h * size.dpr));
    const padX = Math.round(iw * PAD.x);
    const padTop = Math.round(ih * PAD.top);
    const padBottom = Math.round(ih * PAD.bottom);

    canvas.width = iw + padX * 2;
    canvas.height = ih + padTop + padBottom;
    // Hung off the word by exactly the padding, so the raster still sits on
    // top of the vector it replaces.
    canvas.style.width = `${size.w * (1 + PAD.x * 2)}px`;
    canvas.style.height = `${size.h * (1 + PAD.top + PAD.bottom)}px`;
    canvas.style.left = `${-size.w * PAD.x}px`;
    canvas.style.top = `${-size.h * PAD.top}px`;

    ink = { x: padX, y: padTop, w: iw, h: ih };

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, ink.x, ink.y, ink.w, ink.h);
    particles = sample(
      ctx.getImageData(0, 0, canvas.width, canvas.height).data,
      canvas.width,
      ink,
    );
    have = size;

    // A later layout() may have landed while we were decoding.
    void build();
  };

  return {
    layout(cssWidth, cssHeight) {
      want = { w: cssWidth, h: cssHeight, dpr: Math.min(Math.max(window.devicePixelRatio || 1, MIN_DPR), 2) };
      void build();
    },

    isReady: () => particles !== null,

    draw(t) {
      if (!ctx || !particles || !have || !ink) return;
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      // Still intact: the artwork itself, not four thousand squares pretending.
      if (t <= 0.0005) {
        ctx.globalAlpha = 1;
        ctx.drawImage(image, ink.x, ink.y, ink.w, ink.h);
        return;
      }

      const p = particles;
      const dpr = have.dpr;
      const cell = STEP;
      const box = ink;
      // How far from the edge a particle starts giving out. Nothing should
      // ever reach the canvas boundary while it is still visible.
      const topFade = box.y * FADE.top;
      const sideFade = box.x * FADE.side;
      let bucket = -1;

      ctx.fillStyle = '#123e63';
      for (let i = 0; i < p.n; i++) {
        const local = (t - p.delay[i]!) / (1 - p.delay[i]!);
        if (local <= 0) {
          // Not yet airborne — still part of the solid word.
          if (bucket !== 12) {
            ctx.globalAlpha = 1;
            bucket = 12;
          }
          ctx.fillRect(p.x[i]!, p.y[i]!, cell, cell);
          continue;
        }
        if (local >= 1) continue;

        // Squared travel: ink hangs for a beat, then accelerates away.
        const d = local * local * p.reach[i]!;
        const sway = Math.sin(local * 7 + p.phase[i]!) * 9 * dpr * local;
        const x = p.x[i]! + p.dx[i]! * d + sway;
        const y = p.y[i]! + p.dy[i]! * d - local * box.h * 0.9;

        // Two fades multiplied: the particle's own life, and its nearness to
        // the edge of the canvas. The second is what replaces the hard line.
        let alpha = (1 - local) ** 1.5;
        if (y < topFade) alpha *= Math.max(0, y / topFade);
        const edge = Math.min(x, w - x);
        if (edge < sideFade) alpha *= Math.max(0, edge / sideFade);
        if (alpha <= 0.004) continue;

        const b = (alpha * 16) | 0;
        if (b !== bucket) {
          ctx.globalAlpha = alpha;
          bucket = b;
        }

        const size = Math.max(0.7 * dpr, cell * (1 - 0.5 * local));
        ctx.fillRect(x, y, size, size);
      }
      ctx.globalAlpha = 1;
    },

    destroy() {
      dead = true;
      particles = null;
      ink = null;
    },
  };
}
