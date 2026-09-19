// Builds a payload, opens the buyer URL, and checks the page renders it.
import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 430, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => m.type()==='error' && errors.push(m.text()));

await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });

const url = await page.evaluate(async () => {
  const { buyerUrl } = await import('/src/util/qrpayload.ts');
  const listing = {
    id: '5555fe14-3d26-45f9-a37f-8d151f222f5d', client_item_id: 'x', state: 'ready',
    title: 'Handcrafted Bidri-Style Brass Hookah Base with Silver Floral Inlay',
    description: 'This exquisite bell-shaped hookah base is handcrafted using traditional metal inlay techniques reminiscent of Bidriware.',
    image_urls: ['http://localhost:8000/api/v1/listings/5555fe14-3d26-45f9-a37f-8d151f222f5d/media/d38259cd-6737-4e88-800d-9bca24978d00?v=1789814934'],
    fact_sheet: { material:'Brass with Silver Inlay', size:'9 inches (height)', colour:'Black, Silver',
      technique:'Bidriware (Metal Inlay Art)', origin:null, quantity:1, price_in_paise:400000,
      hours_to_make:null, material_cost_in_paise:null, is_one_of_a_kind:false },
    suggestions: [], follow_up_question: null, suggested_price_in_paise: 400000,
    price_floor_in_paise: 360000, preview_url: null, photo_consent: true,
    story_consent: true, views: 0, used_live_model: true,
  };
  return buyerUrl(location.origin, listing, 400000, listing.image_urls);
});
console.log('buyer url length:', url.length);

await page.goto(url, { waitUntil: 'networkidle' });
const title = await page.locator('h1').innerText().catch(()=>'(none)');
const price = await page.locator('[class*="price"]').first().innerText().catch(()=>'(none)');
const facts = await page.locator('[class*="factValue"]').allInnerTexts().catch(()=>[]);
// Media lives on the backend, so with nothing on :8000 the buyer page is
// expected to drop the <img> rather than show a broken-image icon. Absent is
// a pass here; present-but-broken is the failure.
const heroCount = await page.locator('[class*="hero"]').count();
const imgOk = heroCount === 0
  ? 'dropped (backend unreachable — expected)'
  : await page.locator('[class*="hero"]').evaluate(
      (el) => (el.complete && el.naturalWidth > 0 ? 'loaded' : 'BROKEN'),
    );

console.log('title:', title);
console.log('price:', price);
console.log('facts:', facts.join(' | '));
console.log('hero image:', imgOk);
await page.screenshot({ path: '/tmp/kirtikar-shots/B1-buyer.png', fullPage: true });
// Media requests to a backend that is not running are part of the scenario.
const real = errors.filter((e) => !e.includes('ERR_CONNECTION_REFUSED'));
console.log(real.length ? 'ERRORS: ' + real.join(' | ') : 'no page errors');
await browser.close();
