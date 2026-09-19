// Full loop: pick -> speak -> pipeline -> 7-step wizard -> published + QR.
import { chromium } from 'playwright';
const OUT = '/tmp/kirtikar-shots';
const log = (...a) => console.log(...a);

const browser = await chromium.launch({
  args: ['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',
         '--use-file-for-fake-audio-capture=/tmp/speech2.wav'],
});
const ctx = await browser.newContext({ viewport:{width:1600,height:1000}, permissions:['microphone'] });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => m.type()==='error' && errors.push(m.text()));

await page.goto('http://localhost:5173/', { waitUntil:'networkidle' });
await page.getByTitle('Metalwork',{exact:true}).click(); await page.waitForTimeout(900);
await page.getByRole('button',{name:/These photos are good/}).click(); await page.waitForTimeout(300);

const btn = page.getByRole('button',{name:/Hold and speak|Speaking/});
const b = await btn.boundingBox();
await page.mouse.move(b.x+b.width/2, b.y+b.height/2);
await page.mouse.down(); await page.waitForTimeout(9000); await page.mouse.up();
await page.waitForTimeout(2000);
await page.getByRole('button',{name:/This is right/}).click();
log('submitted; waiting for pipeline…');

// Wait for the wizard (up to 3 min).
await page.waitForFunction(
  () => { const h = document.querySelector('h1'); return h && !/writing it up/i.test(h.textContent); },
  undefined,
  { timeout: 190000 },
);
const title = await page.locator('h1').innerText();
log('first wizard screen:', JSON.stringify(title));
await page.screenshot({ path: `${OUT}/W0-first.png` });

// Walk the wizard.
const steps = [
  [/Carry on anyway|All of this is right/, 'W1-readback'],
  [/Yes, add it|This price is right/,      'W2-price'],
  [/This price is right/,                  'W2b-price'],
  [/^Done$/,                               'W3-stock'],
  [/^Done$/,                               'W4-photos'],
  [/^Done$/,                               'W5-preview'],
  [/Put it up for sale/,                   'W6-consent'],
];
for (const [pattern, shot] of steps) {
  const h = await page.locator('h1').innerText().catch(()=>'?');
  const step = await page.locator('[class*="StepProgress-module"] span').last().innerText().catch(()=>'');
  log(`  ${step.padEnd(12)} ${h}`);
  await page.screenshot({ path: `${OUT}/${shot}.png` });
  const target = page.getByRole('button',{name:pattern}).first();
  if (await target.isVisible().catch(()=>false)) { await target.click(); await page.waitForTimeout(700); }
}

await page.waitForTimeout(6000);
const finalTitle = await page.locator('h1').innerText().catch(()=>'?');
log('final:', JSON.stringify(finalTitle));
const hasQr = await page.locator('img[alt*="Scan"]').isVisible().catch(()=>false);
log('QR visible:', hasQr);
await page.screenshot({ path: `${OUT}/W7-published.png` });
log(errors.length ? 'ERRORS: '+errors.slice(0,4).join(' | ') : 'no page errors');
await browser.close();
