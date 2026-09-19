// Submits with no backend running: proves the progression paces correctly
// and that the bar holds below 100 rather than completing or freezing.
import { chromium } from 'playwright';
const OUT = '/tmp/kirtikar-shots';

const browser = await chromium.launch({
  args: ['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',
         '--use-file-for-fake-audio-capture=/tmp/kirtikar-tone.wav'],
});
const ctx = await browser.newContext({ viewport:{width:1600,height:1000}, permissions:['microphone'] });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));

await page.goto('http://localhost:5173/', { waitUntil:'networkidle' });
await page.getByTitle('Pottery',{exact:true}).click(); await page.waitForTimeout(600);
await page.getByRole('button',{name:/These photos are good/}).click(); await page.waitForTimeout(300);
await page.getByRole('button',{name:/Type it instead/}).click(); await page.waitForTimeout(300);
await page.locator('textarea').fill('This is a clay water pot I threw on the wheel. Twelve hundred rupees.');
await page.getByRole('button',{name:/Use this description/}).click();

const readPct = async () => {
  const t = await page.locator('[class*="overallLabel"] span').last().innerText().catch(()=>'-');
  return t;
};
const samples = [];
for (let i=0;i<10;i++){
  await page.waitForTimeout(3000);
  const pct = await readPct();
  const active = await page.locator('[class*="stageLabelActive"]').innerText().catch(()=>'-');
  samples.push(`${(i+1)*3}s: ${pct.padStart(4)} ${active}`);
  if (i===2) await page.screenshot({ path: `${OUT}/f5-processing.png` });
}
console.log(samples.join('\n'));
const done = await page.locator('[class*="stageIcon"] svg').count();
console.log('completed stage ticks:', done);
console.log(errors.length ? 'ERRORS: '+errors.join(' | ') : 'no page errors');
await browser.close();
