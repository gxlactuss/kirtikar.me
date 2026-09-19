import { chromium } from 'playwright';
const browser = await chromium.launch({
  args: ['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture=/tmp/kirtikar-tone.wav'],
});
const ctx = await browser.newContext({ viewport:{width:1600,height:1000}, permissions:['microphone'] });
const page = await ctx.newPage();
await page.goto('http://localhost:5173/', { waitUntil:'networkidle' });
await page.getByTitle('Pottery',{exact:true}).click(); await page.waitForTimeout(600);
await page.getByRole('button',{name:/These photos are good/}).click(); await page.waitForTimeout(300);
const btn = page.getByRole('button',{name:/Hold and speak|Speaking/});
const b = await btn.boundingBox();
await page.mouse.move(b.x+b.width/2, b.y+b.height/2); await page.mouse.down();
// sample bar heights over 3 seconds
const heights = [];
for (let i=0;i<6;i++){
  await page.waitForTimeout(500);
  const hs = await page.locator('[class*="Waveform-module"] span, [class*="bar"]').evaluateAll(
    els => els.slice(0,21).map(e => Math.round(parseFloat(getComputedStyle(e).height)))
  );
  heights.push(Math.max(...hs));
}
await page.mouse.up();
console.log('max bar height per 500ms sample:', heights.join(', '));
console.log(heights.some(h=>h>12) ? 'PASS: waveform responds to audio' : 'FAIL: waveform flat');
await browser.close();
