import { chromium } from 'playwright';
const browser = await chromium.launch();
const errors = [];
async function visit(label, url) {
  const page = await browser.newPage({ viewport: { width: 430, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  await page.goto(url, { waitUntil: 'networkidle' });
  const body = (await page.locator('body').innerText()).replace(/\n+/g,' | ').slice(0,180);
  const imgs = await page.locator('img').count();
  console.log(`\n[${label}]`);
  console.log('  text:', body);
  console.log('  imgs rendered:', imgs, '| pageerrors:', errs.length ? errs.join(';') : 'none');
  await page.close();
}
const b64 = o => Buffer.from(JSON.stringify(o)).toString('base64url');
const O = 'http://localhost:5173';

// 1. payload missing `f` entirely (used to throw -> blank page)
await visit('no facts field', `${O}/?p=${b64({t:'Brass Pot',d:'A pot.',p:250000,i:[]})}`);
// 2. junk fact entries mixed with good ones
await visit('junk facts', `${O}/?p=${b64({t:'Clay Vase',d:'',p:null,f:[['Made of','Clay'],'oops',[1,2],['Size','9 in']],i:[]})}`);
// 3. garbage base64
await visit('garbage payload', `${O}/?p=not-real-base64!!`);
// 4. dead image url -> should drop the img, not show broken icon
await visit('dead image', `${O}/?p=${b64({t:'Woven Mat',d:'',p:100000,f:[],i:['http://127.0.0.1:9/nope.jpg']})}`);
// 5. ?listing= fallback with no backend -> friendly message, not the demo stage
await visit('listing fallback', `${O}/?listing=5555fe14-3d26-45f9-a37f-8d151f222f5d`);
await browser.close();
