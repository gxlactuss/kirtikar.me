// Full loop against the live local backend.
import { chromium } from 'playwright';
const OUT = '/tmp/kirtikar-shots';

const browser = await chromium.launch({
  args: ['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',
         `--use-file-for-fake-audio-capture=${process.env.AUDIO ?? '/tmp/speech2.wav'}`],
});
const ctx = await browser.newContext({ viewport:{width:1600,height:1000}, permissions:['microphone'] });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => m.type()==='error' && errors.push(m.text()));

await page.goto('http://localhost:5173/', { waitUntil:'networkidle' });
await page.getByTitle('Metalwork',{exact:true}).click(); await page.waitForTimeout(800);
await page.getByRole('button',{name:/These photos are good/}).click(); await page.waitForTimeout(300);

// Hold to speak for 9 seconds
const btn = page.getByRole('button',{name:/Hold and speak|Speaking/});
const b = await btn.boundingBox();
await page.mouse.move(b.x+b.width/2, b.y+b.height/2);
await page.mouse.down();
await page.waitForTimeout(9000);
await page.mouse.up();
await page.waitForTimeout(2000);
await page.getByRole('button',{name:/This is right/}).click();

const t0 = Date.now();
let shot = false;
for (let i=0;i<40;i++){
  await page.waitForTimeout(3000);
  const pct = await page.locator('[class*="overallLabel"] span').last().innerText().catch(()=>'-');
  const active = await page.locator('[class*="stageLabelActive"]').innerText().catch(()=>'-');
  const queue = await page.locator('[class*="queueLine"]').innerText().catch(()=>'-');
  const el = Math.round((Date.now()-t0)/1000);
  console.log(`${String(el).padStart(3)}s  ${pct.padStart(4)}  ${active.padEnd(28)} | ${queue.replace(/\n/g,' ')}`);
  if (!shot && el>=12){ await page.screenshot({path:`${OUT}/L1-processing.png`}); shot=true; }
  const title = await page.locator('h1').innerText().catch(()=>'');
  if (/what we understood|One question/i.test(title)) {
    console.log('REACHED REVIEW:', title);
    await page.screenshot({path:`${OUT}/L2-review.png`});
    break;
  }
}
console.log(errors.length ? 'ERRORS: '+errors.slice(0,5).join(' | ') : 'no page errors');
await browser.close();
