// ?demo=1 must replay a recording without ever calling the backend.
import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const apiCalls = [];
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
page.on('request', r => { if (r.url().includes(':8000')) apiCalls.push(r.url()); });

await page.goto('http://localhost:5173/?demo=1', { waitUntil: 'networkidle' });
console.log('chip:', await page.locator('[class*="chip"]').first().innerText().catch(()=>'(none)'));

await page.getByTitle('Pottery', { exact: true }).click();
await page.waitForTimeout(700);
await page.getByRole('button', { name: /These photos are good|Use these photos/ }).click();
await page.waitForTimeout(300);
await page.getByRole('button', { name: /Type it instead/ }).click();
await page.waitForTimeout(300);
await page.getByRole('textbox').fill('A clay water pot.');
await page.getByRole('button', { name: /Use this description/ }).click();
console.log('submitted; waiting for the replay to finish…');

try {
  await page.locator('h1').filter({ hasText: /Anything look wrong|Is this right|Check/i })
    .first().waitFor({ timeout: 120_000 });
} catch {
  // Any heading that is not the processing one means the wizard took over.
  await page.waitForFunction(
    () => { const h = document.querySelector('h1'); return h && !/writing it up|cleaning|listening|price|checking it over/i.test(h.textContent); },
    { timeout: 60_000 },
  ).catch(() => {});
}
console.log('landed on:', await page.locator('h1').innerText().catch(()=>'(none)'));
console.log('chip now:', await page.locator('[class*="chip"]').first().innerText().catch(()=>'(none)'));
console.log('backend calls made:', apiCalls.length ? apiCalls.join(' | ') : 'NONE (correct)');
console.log(errors.length ? 'pageerrors: ' + errors.join(' | ') : 'no page errors');
await browser.close();
