// With no backend AND no fixtures, the seller must still get out of the
// processing screen instead of watching a frozen bar.
import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
await page.getByTitle('Metalwork', { exact: true }).click();
await page.waitForTimeout(800);
await page.getByRole('button', { name: /These photos are good|Use these photos/ }).click();
await page.waitForTimeout(400);
await page.getByRole('button', { name: /Type it instead/ }).click();
await page.waitForTimeout(400);
await page.getByRole('textbox').fill('A brass pot I made by hand.');
await page.getByRole('button', { name: /Use this description/ }).click();
console.log('submitted, waiting for the failure path…');
try {
  await page.getByRole('button', { name: /Start again/ }).waitFor({ timeout: 90_000 });
  console.log('PASS: recovery button appeared');
  console.log('heading:', await page.locator('h1').innerText());
  await page.getByRole('button', { name: /Start again/ }).click();
  await page.waitForTimeout(600);
  console.log('after reset, heading:', await page.locator('h1').innerText());
} catch {
  console.log('FAIL: still stuck on', await page.locator('h1').innerText());
}
console.log(errors.length ? 'pageerrors: ' + errors.join(' | ') : 'no page errors');
await browser.close();
