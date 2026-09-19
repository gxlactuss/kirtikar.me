// Drives the demo like a visitor and screenshots each step.
import { chromium } from 'playwright';

const URL = process.env.URL ?? 'http://localhost:5173/';
const OUT = process.env.OUT ?? '/tmp/kirtikar-shots';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const errors = [];
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
page.on('pageerror', (e) => errors.push(String(e)));

await page.goto(URL, { waitUntil: 'networkidle' });
await page.screenshot({ path: `${OUT}/f0-empty.png` });

// Pick two crafts from the rail.
await page.getByTitle('Pottery', { exact: true }).click();
await page.waitForTimeout(700);
await page.getByTitle('Handloom', { exact: true }).click();
await page.waitForTimeout(700);
await page.screenshot({ path: `${OUT}/f1-picked.png` });

const rows = await page.locator('[class*="photoRow"]').count();
console.log(`photo rows rendered: ${rows}`);

if (errors.length) {
  console.log('CONSOLE ERRORS:');
  for (const e of errors) console.log('  ' + e);
} else {
  console.log('no console errors');
}
await browser.close();
