// Frame-by-frame stills of the opening sequence, at fixed scroll fractions.
//
// The intro is driven entirely by scroll position, so it can be inspected by
// jumping to a fraction of the track and waiting for the chase to settle —
// no video capture, and every run lands on exactly the same frames.
import { chromium } from 'playwright';

const URL = process.env.URL ?? 'http://localhost:5173/';
const OUT = process.env.OUT ?? '/tmp/kirtikar-intro';
const FRACTIONS = [0.08, 0.16, 0.24, 0.34, 0.42, 0.55, 0.72, 0.86, 0.95];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.waitForTimeout(1600); // the entrance settles

const name = (f) => `${OUT}/i${String(Math.round(f * 100)).padStart(2, '0')}.png`;
await page.screenshot({ path: `${OUT}/i00.png` });

const max = await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
console.log(`track: ${max}px (${(max / 900).toFixed(2)} viewports of scroll)`);

for (const f of [...FRACTIONS, 1]) {
  await page.evaluate((y) => window.scrollTo(0, y), Math.round(max * f));
  await page.waitForTimeout(700);
  await page.screenshot({ path: name(f) });
}

console.log(`wrote ${FRACTIONS.length + 2} frames to ${OUT}`);
console.log('errors:', errors.length ? errors : 'none');
await browser.close();
