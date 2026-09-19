// Screenshot + measure the phone viewport at each device preset.
// Proves the frame RESIZES (content box tracks the preset) rather than
// merely SCALING (content box would stay put while pixels stretch).
import { chromium } from 'playwright';

const URL = process.env.URL ?? 'http://localhost:5173/';
const OUT = process.env.OUT ?? '/tmp/kirtikar-shots';
const presets = [1, 2, 3, 4, 5];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const errors = [];
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
page.on('pageerror', (e) => errors.push(String(e)));

await page.goto(URL, { waitUntil: 'networkidle' });

for (const key of presets) {
  await page.keyboard.press(String(key));
  await page.waitForTimeout(400);

  const info = await page.evaluate(() => {
    const vp = document.querySelector('[data-device]');
    const r = vp.getBoundingClientRect();
    const cs = getComputedStyle(vp);
    return {
      claimed: Number(vp.dataset.width),
      id: vp.dataset.device,
      cssWidth: parseFloat(cs.width),      // layout width, unaffected by transform
      paintedWidth: Math.round(r.width),   // after the optical zoom
      fontSize: cs.fontSize,
    };
  });

  const ok = info.cssWidth === info.claimed;
  console.log(
    `${ok ? 'PASS' : 'FAIL'}  ${info.id.padEnd(9)} claimed=${info.claimed} ` +
      `layout=${info.cssWidth} painted=${info.paintedWidth} font=${info.fontSize}`,
  );
  await page.screenshot({ path: `${OUT}/${key}-${info.id}.png` });
}

if (errors.length) {
  console.log('\nCONSOLE ERRORS:');
  for (const e of errors) console.log('  ' + e);
}
await browser.close();
