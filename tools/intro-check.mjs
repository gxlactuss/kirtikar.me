// The intro's exits, in every way a visitor can take them.
//
// Each of these has a way to strand someone on a four-screen-tall page with
// no demo under it, which is the one failure a judge arriving unannounced
// cannot recover from. Run it against a dev server or a built preview.
import { chromium } from 'playwright';

const URL = process.env.URL ?? 'http://localhost:5173/';
const OUT = process.env.OUT ?? '/tmp/kirtikar-intro';

const browser = await chromium.launch();
const errors = [];
const fails = [];

const open = async (opts = {}) => {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, ...opts });
  page.on('pageerror', (e) => errors.push(`PAGEERROR ${e}`));
  page.on('console', (m) => {
    // The backend being absent is not this script's business.
    if (m.type() === 'error' && !m.text().includes('ERR_CONNECTION')) errors.push(m.text());
  });
  return page;
};

const state = (page) =>
  page.evaluate(() => ({
    scrollable: document.documentElement.scrollHeight - window.innerHeight,
    introRunning: document.documentElement.classList.contains('introRunning'),
    seen: sessionStorage.getItem('kirtikar:intro-seen'),
    stageLive: !!document.querySelector('[class*=stageWrap][data-landed="1"]'),
  }));

const check = (what, ok) => {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`);
  if (!ok) fails.push(what);
};

// --- the boundary: the phone is visibly off until the scroll ends ---
{
  const b = await open();
  await b.goto(URL, { waitUntil: 'networkidle' });
  await b.waitForTimeout(1400);
  const max = await b.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
  await b.evaluate((y) => window.scrollTo(0, y), Math.round(max * 0.88));
  await b.waitForTimeout(900);
  const before = await b.evaluate(() => {
    const h = document.querySelector('[class*=handoff]');
    const w = document.querySelector('[class*=stageWrap]');
    return {
      state: h?.dataset.state,
      shown: Number(getComputedStyle(h).opacity) > 0.5,
      text: h?.textContent,
      dimmed: getComputedStyle(w).filter !== 'none',
      clickable: getComputedStyle(w).pointerEvents !== 'none',
    };
  });
  check('near the end, the bar says to keep scrolling', before.state === 'gate' && before.shown && /Keep scrolling/.test(before.text));
  check('near the end, the phone is greyed and not clickable', before.dimmed && !before.clickable);

  await b.evaluate(() => window.scrollTo(0, 1e6));
  await b.waitForTimeout(1500);
  const after = await b.evaluate(() => {
    const h = document.querySelector('[class*=handoff]');
    const w = document.querySelector('[class*=stageWrap]');
    return {
      state: h?.dataset.state,
      shown: Number(getComputedStyle(h).opacity) > 0.5,
      text: h?.textContent,
      dimmed: getComputedStyle(w).filter !== 'none',
      handoffClickThrough: getComputedStyle(h).pointerEvents === 'none',
    };
  });
  check('at the end, the bar says the demo is live', after.state === 'live' && after.shown && /Your turn/.test(after.text));
  check('at the end, the phone is in full colour', !after.dimmed);
  check('the live marker never blocks a click', after.handoffClickThrough);
  await b.screenshot({ path: `${OUT}/c-boundary-live.png` });

  await b.mouse.click(10, 450);
  await b.waitForTimeout(700);
  const gone = await b.evaluate(() => document.querySelector('[class*=handoff]')?.dataset.state);
  check('the first click puts the marker away', gone === 'done');
  await b.close();
}

// --- skip lands, and the demo underneath actually works ---
const page = await open();
await page.goto(URL, { waitUntil: 'networkidle' });
await page.waitForTimeout(1400);
await page.click('text=Skip to the demo');
await page.waitForTimeout(2500);
let s = await state(page);
check('skip lands on the demo', s.stageLive && !s.introRunning);
check('landing leaves nothing to scroll', s.scrollable === 0);

await page.locator('input[type=file]').setInputFiles('public/fixtures/pottery/photo_1.jpg');
await page.waitForTimeout(900);
check(
  'the picker is usable after landing',
  await page.evaluate(() => !!document.querySelector('img[src^="blob:"]')),
);
await page.screenshot({ path: `${OUT}/c-after-skip.png` });

// --- replay re-arms the whole sequence ---
await page.click('text=Replay intro');
await page.waitForTimeout(1600);
s = await state(page);
check('replay re-arms the track', s.introRunning && s.scrollable > 0 && s.seen === null);

// --- a reload mid-demo must not cost the visitor the scroll again ---
await page.evaluate(() => window.scrollTo(0, 1e6));
await page.waitForTimeout(1500);
await page.reload({ waitUntil: 'networkidle' });
await page.waitForTimeout(600);
s = await state(page);
check('reload after landing goes straight to the demo', s.stageLive && s.scrollable === 0);

// --- motion the visitor asked not to see ---
const reduced = await open({ reducedMotion: 'reduce' });
await reduced.goto(URL, { waitUntil: 'networkidle' });
await reduced.waitForTimeout(600);
check('reduced motion skips the sequence', (await state(reduced)).stageLive);

// --- a phone ---
const phone = await open({ viewport: { width: 390, height: 844 } });
await phone.goto(URL, { waitUntil: 'networkidle' });
await phone.waitForTimeout(1500);
await phone.screenshot({ path: `${OUT}/c-phone-hero.png` });
const max = await phone.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
await phone.evaluate((y) => window.scrollTo(0, y), Math.round(max * 0.45));
await phone.waitForTimeout(900);
await phone.screenshot({ path: `${OUT}/c-phone-guide.png` });
check(
  'the guide fits a phone without scrolling sideways',
  await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
);

// --- Escape is the other way out ---
{
  const e = await open();
  await e.goto(URL, { waitUntil: 'networkidle' });
  await e.waitForTimeout(1400);
  await e.keyboard.press('Escape');
  check('Escape lands on the demo', (await landedWithin(e, 1500)) !== null);
  await e.close();
}

// --- real phones ------------------------------------------------------------
//
// A phone is where the scroll range moves under the visitor's thumb: the
// toolbar hides and reappears, the page rubber-bands at the bottom, and the
// window, the layout viewport and the visual viewport each report a
// different height. Every case here ends with the visitor genuinely at the
// bottom of the page, and every one of them has to land.
//
// Chromium's emulation lets svh follow the window, which a real toolbar does
// not. The "pinned" cases fix the track at its first height in px before the
// window changes, so the page stays the same length while the viewport
// grows or shrinks around it — which is what Safari and Chrome on a phone do.

async function landedWithin(page, ms) {
  const t0 = Date.now();
  for (;;) {
    if ((await state(page)).stageLive) return Date.now() - t0;
    if (Date.now() - t0 > ms) return null;
    await page.waitForTimeout(40);
  }
}

async function phonePage(w, h) {
  const ctx = await browser.newContext({
    viewport: { width: w, height: h },
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 2,
  });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errors.push(`PAGEERROR ${e}`));
  p.on('console', (m) => {
    if (m.type() === 'error' && !m.text().includes('ERR_CONNECTION')) errors.push(m.text());
  });
  await p.goto(URL, { waitUntil: 'networkidle' });
  await p.waitForTimeout(1300);
  return { p, ctx };
}

const pinTrack = (p) =>
  p.evaluate(() => {
    const t = document.querySelector('div[data-landed]:not([data-arrived])');
    t.style.height = `${t.getBoundingClientRect().height}px`;
  });

const bottomOf = (p) =>
  p.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);

async function swipeUp(cdp, x, from, to, steps = 10) {
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y: from }] });
  for (let i = 1; i <= steps; i++) {
    const y = from + ((to - from) * i) / steps;
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y }] });
    // Paced like a finger. Sent back to back, the moves arrive inside one
    // frame and the compositor never starts a scroll from them.
    await new Promise((r) => setTimeout(r, 16));
  }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
}

const TOOLBAR = 110;

for (const [w, h] of [
  [320, 568],
  [360, 800],
  [390, 844],
  [768, 1024],
]) {
  const tag = `${w}x${h}`;

  // a) a thumb, swiping, until the page will not go any further
  {
    const { p, ctx } = await phonePage(w, h);
    const cdp = await ctx.newCDPSession(p);
    // The furthest the page got, recorded as it goes: landing collapses the
    // track and puts scrollY back to 0, so it cannot be read afterwards.
    await p.evaluate(() => {
      window.__furthest = 0;
      addEventListener('scroll', () => (window.__furthest = Math.max(window.__furthest, scrollY)));
    });
    let swipes = 0;
    while (swipes < 20 && !(await state(p)).stageLive) {
      await swipeUp(cdp, Math.round(w / 2), Math.round(h * 0.75), Math.round(h * 0.2));
      await p.waitForTimeout(350);
      swipes++;
    }
    const ms = await landedWithin(p, 1500);
    const furthest = await p.evaluate(() => window.__furthest);
    check(
      `${tag} a) touch swipes to the bottom land (${swipes} swipes, furthest ${Math.round(furthest)}px)`,
      furthest > 0 && ms !== null,
    );
    const fill = await p.evaluate(() =>
      getComputedStyle(document.querySelector('[class*=handoff]')).getPropertyValue('--fill').trim(),
    );
    check(`${tag} a) the gate bar ends full`, fill === '1');
    await ctx.close();
  }

  // b) toolbar showing, scroll partway, toolbar collapses, scroll to the end
  for (const pinned of [false, true]) {
    const { p, ctx } = await phonePage(w, h - TOOLBAR);
    if (pinned) await pinTrack(p);
    await p.evaluate((y) => window.scrollTo(0, y), Math.round((await bottomOf(p)) * 0.4));
    await p.waitForTimeout(300);
    await p.setViewportSize({ width: w, height: h });
    await p.waitForTimeout(200);
    await p.evaluate(() => window.scrollTo(0, 1e6));
    check(`${tag} b) toolbar collapses mid-scroll${pinned ? ' (pinned)' : ''}, bottom lands`, (await landedWithin(p, 1500)) !== null);
    await ctx.close();
  }

  // c) at the bottom, the toolbar comes back
  for (const pinned of [false, true]) {
    const { p, ctx } = await phonePage(w, h);
    if (pinned) await pinTrack(p);
    await p.evaluate(() => window.scrollTo(0, 1e6));
    await p.setViewportSize({ width: w, height: h - TOOLBAR });
    check(`${tag} c) toolbar reappears at the bottom${pinned ? ' (pinned)' : ''}, lands`, (await landedWithin(p, 1500)) !== null);
    await ctx.close();
  }

  // d) the rubber band: at the bottom, then settled a few px short of it
  {
    const { p, ctx } = await phonePage(w, h);
    // The allowance is for a bounce, not a shortcut: a visitor who has
    // stopped a thumb's width short is still being shown the way down.
    await p.evaluate(() =>
      window.scrollTo(0, document.documentElement.scrollHeight - window.innerHeight - 40),
    );
    await p.waitForTimeout(700);
    check(`${tag} d) stopping 40px short does not land`, !(await state(p)).stageLive);
    await p.evaluate(() => {
      const b = document.documentElement.scrollHeight - window.innerHeight;
      window.scrollTo(0, b);
      window.scrollTo(0, b - 6);
    });
    check(`${tag} d) a bounce that settles 6px short still lands`, (await landedWithin(p, 1500)) !== null);
    await ctx.close();
  }

  // e) a page longer than the track
  {
    const { p, ctx } = await phonePage(w, h);
    await p.evaluate(() => {
      const extra = document.createElement('div');
      extra.style.height = '50px';
      document.body.append(extra);
    });
    await p.evaluate(() => window.scrollTo(0, 1e6));
    check(`${tag} e) a page 50px longer than the track lands at its true bottom`, (await landedWithin(p, 1500)) !== null);
    await ctx.close();
  }

  // f) tapping skip, with the smooth scroll working, off, or refused
  for (const mode of ['smooth', 'scroll-behavior auto', 'scrollTo stubbed']) {
    const { p, ctx } = await phonePage(w, h);
    if (mode === 'scroll-behavior auto') {
      await p.addStyleTag({ content: 'html { scroll-behavior: auto !important; }' });
      await p.evaluate(() => {
        const real = window.scrollTo.bind(window);
        window.scrollTo = (a, b) =>
          typeof a === 'object' ? real({ ...a, behavior: 'auto' }) : real(a, b);
      });
    }
    if (mode === 'scrollTo stubbed') await p.evaluate(() => (window.scrollTo = () => {}));
    await p.tap('text=Skip to the demo');
    const ms = await landedWithin(p, 1500);
    check(`${tag} f) skip (${mode}) lands${ms !== null ? ` in ${ms}ms` : ''}`, ms !== null);
    await ctx.close();
  }
}

// --- a skip that is still in flight must not land a replayed intro ---
{
  const { p, ctx } = await phonePage(390, 844);
  await p.tap('text=Skip to the demo');
  const ms = await landedWithin(p, 1500);
  await p.tap('text=Replay intro');
  await p.waitForTimeout(1300);
  const s2 = await state(p);
  check(`replay straight after a skip stays on the intro (landed in ${ms}ms)`, ms !== null && s2.introRunning && !s2.stageLive);
  // And the replayed run still lands by scrolling.
  await p.evaluate(() => window.scrollTo(0, 1e6));
  check('the replayed run lands again at the bottom', (await landedWithin(p, 1500)) !== null);
  await ctx.close();
}

console.log('errors:', errors.length ? errors : 'none');
await browser.close();
process.exit(fails.length || errors.length ? 1 : 0);
