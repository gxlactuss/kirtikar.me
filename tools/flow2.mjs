import { chromium } from 'playwright';
const OUT = '/tmp/kirtikar-shots';

const browser = await chromium.launch({
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
         '--autoplay-policy=no-user-gesture-required'],
});
const ctx = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  permissions: ['microphone'],
});
const page = await ctx.newPage();
const errors = [];
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
page.on('pageerror', (e) => errors.push(String(e)));

await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
await page.getByTitle('Pottery', { exact: true }).click();
await page.waitForTimeout(600);
await page.getByRole('button', { name: /These photos are good/ }).click();
await page.waitForTimeout(400);
await page.screenshot({ path: `${OUT}/f2-voice.png` });

// Hold to speak for 5s using the fake mic device.
const btn = page.getByRole('button', { name: /Hold and speak|Speaking/ });
const box = await btn.boundingBox();
await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
await page.mouse.down();
await page.waitForTimeout(1200);
await page.screenshot({ path: `${OUT}/f3-recording.png` });
await page.waitForTimeout(4000);
await page.mouse.up();
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT}/f4-recorded.png` });

const hasPlayback = await page.getByText('What you said').isVisible().catch(() => false);
console.log('playback row visible:', hasPlayback);
const secs = await page.locator('[class*="playMeta"]').innerText().catch(() => '(none)');
console.log('duration text:', secs.replace(/\n/g, ' | '));

console.log(errors.length ? 'ERRORS:\n  ' + errors.join('\n  ') : 'no console errors');
await browser.close();
