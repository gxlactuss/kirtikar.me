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

console.log('errors:', errors.length ? errors : 'none');
await browser.close();
process.exit(fails.length || errors.length ? 1 : 0);
