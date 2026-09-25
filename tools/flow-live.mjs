// The whole demo, driven like a visitor: pick one photo, speak (or type),
// answer whatever is missing in writing, and read the finished product.
//
//   npm run dev            # in another terminal, with VITE_API_BASE set
//   AUDIO=clip.wav node tools/flow-live.mjs
//
// Env:
//   URL      page to open (default http://localhost:5173/); add ?demo=1 to
//            force the recorded run
//   AUDIO    WAV fed to the fake microphone; without it the description is
//            typed instead
//   TYPED    the typed description when AUDIO is unset
//   UPLOAD   upload this file instead of picking the first catalog product
//   OUT      where screenshots go (default /tmp/kirtikar-shots)
//   DIE=1    fake the create and upload, then answer the status poll with
//            404, as a server that restarted mid-run does; the recorded run
//            must take over. Makes no pipeline call.
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const PAGE = process.env.URL ?? 'http://localhost:5173/';
const OUT = process.env.OUT ?? '/tmp/kirtikar-shots';
const AUDIO = process.env.AUDIO;
const UPLOAD = process.env.UPLOAD;
const TYPED = process.env.TYPED ?? 'This is a brass hookah base I made by hand. It took a week.';
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({
  args: AUDIO
    ? [
        '--use-fake-ui-for-media-stream',
        '--use-fake-device-for-media-stream',
        `--use-file-for-fake-audio-capture=${AUDIO}`,
      ]
    : [],
});
const ctx = await browser.newContext({
  viewport: process.env.PHONE ? { width: 390, height: 844 } : { width: 1600, height: 1000 },
  permissions: AUDIO ? ['microphone'] : [],
});
// Land past the intro, as a returning visitor would.
await ctx.addInitScript(() => sessionStorage.setItem('kirtikar:intro-seen', '1'));
const page = await ctx.newPage();
const errors = [];
const api = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
page.on('request', (r) => r.url().includes('/api/v1/') && api.push(`${r.method()} ${new URL(r.url()).pathname}`));

if (process.env.DIE === '1') {
  const json = (route, body, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  await page.route('**/api/v1/listings', (r) =>
    r.request().method() === 'POST' ? json(r, { id: 'dead-listing' }) : r.continue(),
  );
  await page.route('**/api/v1/listings/dead-listing/media', (r) => json(r, { id: 'm', status: 'uploaded' }));
  await page.route('**/api/v1/listings/dead-listing/status', (r) => json(r, { detail: 'Listing not found' }, 404));
}

const heading = () => page.locator('h1').first().innerText().catch(() => '');
const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png` });
let failures = 0;
const check = (name, ok, detail = '') => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
  if (!ok) failures++;
};

await page.goto(PAGE, { waitUntil: 'networkidle' });
check('opens on step 1', /Pick a product/.test(await heading()), await heading());
check('no continue button before a photo', (await page.getByRole('button', { name: 'Use this photo' }).count()) === 0);
await shot('1-pick-empty');

// --- step 1: exactly one photo ---
const tiles = page.locator('button[data-product]');
const tileCount = await tiles.count();
console.log(`      catalog tiles: ${tileCount}`);
if (UPLOAD) {
  await page.locator('input[type=file]').setInputFiles(UPLOAD);
} else {
  await tiles.nth(0).click();
  await page.waitForTimeout(600);
  if (tileCount > 1) {
    await tiles.nth(1).click(); // picking another replaces the first
  }
}
await page.getByRole('button', { name: 'Use this photo' }).waitFor({ timeout: 10_000 });
const pressed = await page.locator('button[data-product][aria-pressed=true]').count();
check('one photo chosen', UPLOAD ? pressed === 0 : pressed === 1, `${pressed} pressed`);
await shot('1-pick-chosen');
await page.getByRole('button', { name: 'Use this photo' }).click();

// --- step 2: the voice note ---
check('step 2 is the voice note', /Now say what it is/.test(await heading()));
const guide = await page.getByText('Things you can talk about').locator('..').innerText();
check(
  "voice guide is the app's",
  ['Name of the item', 'Colour', 'Height', 'Time taken to make it', 'What the materials cost'].every((g) =>
    guide.includes(g),
  ),
  guide.replace(/\n/g, ' | '),
);
await shot('2-voice');

if (AUDIO) {
  const btn = page.getByRole('button', { name: /Hold and speak|Speaking/ });
  const b = await btn.boundingBox();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(Number(process.env.HOLD_MS ?? 9000));
  await page.mouse.up();
  await page.getByRole('button', { name: 'This is right' }).waitFor({ timeout: 10_000 });
  await shot('2-voice-recorded');
  await page.getByRole('button', { name: 'This is right' }).click();
} else {
  await page.getByRole('button', { name: /Type it instead/ }).click();
  await page.getByRole('textbox').fill(TYPED);
  await page.getByRole('button', { name: /Use this description/ }).click();
}

// --- the pipeline ---
const t0 = Date.now();
let processingShot = false;
for (;;) {
  const h = await heading();
  if (/question|could not finish|This is your product/i.test(h)) break;
  if (/did not work/i.test(h)) break;
  if (Date.now() - t0 > 240_000) break;
  if (!processingShot && Date.now() - t0 > 8_000) {
    await shot('3-processing');
    processingShot = true;
  }
  await page.waitForTimeout(1000);
}
const chip = await page.locator('[class*="chip"]').first().innerText().catch(() => '');
console.log(`      pipeline answered in ${Math.round((Date.now() - t0) / 1000)}s; chip: ${chip.replace(/\n/g, ' ')}`);

// --- step 3: typed answers only ---
let h = await heading();
if (/question/i.test(h)) {
  await shot('3-missing');
  const inputs = page.locator('form input');
  const names = await inputs.evaluateAll((els) => els.map((e) => e.name));
  console.log(`      asked for: ${names.join(', ')}`);
  check('step 3 has no microphone', (await page.getByRole('button', { name: /speak|Hold/i }).count()) === 0);
  const sample = { material: 'Brass', size: '9 inches tall', colour: 'Golden', origin: 'Moradabad', price: 'abc' };
  for (const name of names) await page.locator(`input[name=${name}]`).fill(sample[name] ?? 'x');
  if (names.includes('price')) {
    await page.locator('input[name=price]').blur();
    check('bad price blocks submit', await page.getByRole('button', { name: 'Show my product' }).isDisabled());
    await page.locator('input[name=price]').fill('₹3,500');
  }
  await page.getByRole('button', { name: 'Show my product' }).click();
  await page.locator('h1', { hasText: 'This is your product' }).waitFor({ timeout: 20_000 });
} else if (/could not finish/i.test(h)) {
  await shot('3-halted');
  console.log('      halted: ' + (await page.locator('[class*="panel"]').first().innerText()));
}

// --- step 4: the product ---
h = await heading();
check('ends on the product', /This is your product/.test(h), h);
if (/This is your product/.test(h)) {
  const card = await page.locator('article').innerText();
  console.log('      ' + card.replace(/\n+/g, '\n      '));
  const img = page.locator('article img');
  if (await img.count()) {
    // The processed image comes from the API's region, not the site's, and
    // takes a moment; wait for it rather than judging a half-drawn frame.
    const ok = await img
      .evaluate(
        (el) =>
          new Promise((resolve) => {
            if (el.complete) return resolve(el.naturalWidth > 0);
            el.addEventListener('load', () => resolve(true), { once: true });
            el.addEventListener('error', () => resolve(false), { once: true });
            setTimeout(() => resolve(false), 15_000);
          }),
      )
      .catch(() => false);
    check('product image loads', ok, await img.getAttribute('src'));
  }
  check('no ONDC or publishing step', !/ONDC|Put it up for sale|QR/i.test(await page.locator('body').innerText()));
  await page.locator('[class*="body"]').first().evaluate((el) => el.scrollTo(0, 0));
  await shot('4-final');
  await page.locator('[class*="body"]').first().evaluate((el) => el.scrollTo(0, el.scrollHeight));
  await shot('4-final-bottom');

  await page.getByRole('button', { name: 'Make another product' }).click();
  check('make another returns to step 1', /Pick a product/.test(await heading()));
}

console.log('      api calls: ' + (api.length ? [...new Set(api.map((a) => a.replace(/[0-9a-f-]{36}/g, ':id')))].join(', ') : 'none'));
console.log(errors.length ? 'page errors: ' + errors.slice(0, 5).join(' | ') : '      no page errors');
console.log(failures ? `\n${failures} FAILED` : '\nall passed');
await browser.close();
process.exit(failures ? 1 : 0);
