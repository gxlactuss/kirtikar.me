// The hold-to-speak button, held the way a thumb holds it on a phone.
//
// Every case here is a way the button used to strand someone: a release that
// lands while the permission prompt is still up, a press on iOS where the
// meter's AudioContext never wakes, a finger that wobbles, a touch the system
// cancels, a key that repeats. Touches go through CDP rather than
// locator.click() because only real touchStart/touchEnd pairs exercise the
// pointer capture and cancel paths a phone takes.
//
//   npm run dev            # in another terminal
//   node tools/mic-check.mjs
//
// Env:
//   URL   page to open (default http://localhost:5173/)
import { chromium } from 'playwright';

const URL = process.env.URL ?? 'http://localhost:5173/';

const browser = await chromium.launch({
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
});
const errors = [];
const fails = [];

const check = (what, ok, detail = '') => {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}${ok || !detail ? '' : `  (${detail})`}`);
  if (!ok) fails.push(what);
};

// Counts every stream and recorder the page opens, so a case can ask whether
// anything is still listening after the button says it has stopped.
function instrument() {
  const w = window;
  w.__mic = { streams: [], recorders: [], gum: 0 };
  const md = navigator.mediaDevices;
  const gum = md.getUserMedia.bind(md);
  md.getUserMedia = async (c) => {
    w.__mic.gum++;
    const delay = w.__gumDelay ?? 0;
    if (delay) await new Promise((r) => setTimeout(r, delay));
    const s = await gum(c);
    w.__mic.streams.push(s);
    return s;
  };
  const MR = w.MediaRecorder;
  w.MediaRecorder = class extends MR {
    constructor(...a) {
      super(...a);
      w.__mic.recorders.push(this);
    }
  };
}

const micState = (page) =>
  page.evaluate(() => ({
    gum: window.__mic.gum,
    recorders: window.__mic.recorders.length,
    recordingNow: window.__mic.recorders.filter((r) => r.state === 'recording').length,
    liveTracks: window.__mic.streams.flatMap((s) => s.getTracks()).filter((t) => t.readyState === 'live')
      .length,
  }));

async function openVoice({ gumDelay = 0, hangResume = false } = {}) {
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    permissions: ['microphone'],
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(`PAGEERROR ${e}`));
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().includes('ERR_CONNECTION')) errors.push(m.text());
  });
  await page.addInitScript(() => sessionStorage.setItem('kirtikar:intro-seen', '1'));
  await page.addInitScript(instrument);
  if (gumDelay) await page.addInitScript((d) => (window.__gumDelay = d), gumDelay);
  if (hangResume) {
    // iOS Safari's answer to a context resumed outside a gesture: it stays
    // suspended and the promise never settles.
    await page.addInitScript(() => {
      Object.defineProperty(BaseAudioContext.prototype, 'state', { get: () => 'suspended' });
      AudioContext.prototype.resume = () => new Promise(() => {});
    });
  }
  await page.goto(URL, { waitUntil: 'networkidle' });
  await page.locator('input[type=file]').first().setInputFiles('public/fixtures/pottery/photo_1.jpg');
  await page.getByRole('button', { name: 'Use this photo' }).tap();
  const button = page.getByRole('button', { name: /Hold and speak|Speaking/ });
  await button.waitFor({ timeout: 10000 });
  const box = await button.boundingBox();
  const cdp = await ctx.newCDPSession(page);
  const at = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const touch = (type, dx = 0, dy = 0) =>
    cdp.send('Input.dispatchTouchEvent', {
      type,
      touchPoints: type === 'touchEnd' || type === 'touchCancel' ? [] : [{ x: at.x + dx, y: at.y + dy }],
    });
  // CDP describes every finger still down; ids keep them apart.
  const fingers = (type, points) =>
    cdp.send('Input.dispatchTouchEvent', {
      type,
      touchPoints: points.map(([id, dx]) => ({ id, x: at.x + dx, y: at.y })),
    });
  const label = () => button.innerText();
  const said = page.getByText('What you said');
  return { ctx, page, button, touch, fingers, label, said };
}

// --- a) hold four seconds, let go: a clip comes back ---
{
  const t = await openVoice();
  await t.touch('touchStart');
  await t.page.waitForTimeout(1500);
  check('a) while held, the button says it is listening', /Speaking/.test(await t.label()));
  await t.page.waitForTimeout(2500);
  await t.touch('touchEnd');
  const got = await t.said.waitFor({ timeout: 6000 }).then(() => true, () => false);
  check('a) releasing after 4s shows "What you said"', got);
  check('a) the button is back to "Hold and speak"', /Hold and speak/.test(await t.label()));
  const m = await micState(t.page);
  check('a) the microphone is released', m.recordingNow === 0 && m.liveTracks === 0, JSON.stringify(m));
  await t.ctx.close();
}

// --- b) let go while getUserMedia is still pending ---
{
  const t = await openVoice({ gumDelay: 1500 });
  await t.touch('touchStart');
  await t.page.waitForTimeout(300);
  await t.touch('touchEnd');
  await t.page.waitForTimeout(3000);
  const text = await t.label();
  check('b) an early release does not leave the button saying "Speaking…"', !/Speaking/.test(text), text);
  const m = await micState(t.page);
  check('b) nothing is recording and no track is live', m.recordingNow === 0 && m.liveTracks === 0, JSON.stringify(m));
  const hint = await t.page.getByText(/Hold the button down while you speak/).isVisible();
  check('b) the visitor is told to hold the button while speaking', hint);

  // The next press, with the permission now granted, records normally.
  await t.page.evaluate(() => (window.__gumDelay = 0));
  await t.touch('touchStart');
  await t.page.waitForTimeout(4000);
  await t.touch('touchEnd');
  const got = await t.said.waitFor({ timeout: 6000 }).then(() => true, () => false);
  check('b) the press after that records normally', got);
  await t.ctx.close();
}

// --- c) a thumb that wobbles a few px while holding ---
{
  const t = await openVoice();
  await t.touch('touchStart');
  for (let i = 0; i < 20; i++) {
    await t.page.waitForTimeout(200);
    await t.touch('touchMove', ((i % 5) - 2) * 3, ((i % 3) - 1) * 4);
  }
  check('c) still listening after 4s of wobble', /Speaking/.test(await t.label()));
  await t.touch('touchEnd');
  const got = await t.said.waitFor({ timeout: 6000 }).then(() => true, () => false);
  check('c) the wobbly hold still produces a recording', got);
  await t.ctx.close();
}

// --- d) the system cancels the touch mid-hold ---
{
  const t = await openVoice();
  await t.touch('touchStart');
  await t.page.waitForTimeout(3500);
  check('d) listening before the cancel', /Speaking/.test(await t.label()));
  await t.touch('touchCancel');
  await t.page.waitForTimeout(2000);
  check('d) after touchcancel the button is back to "Hold and speak"', /Hold and speak/.test(await t.label()));
  const m = await micState(t.page);
  check('d) nothing is left recording', m.recordingNow === 0 && m.liveTracks === 0, JSON.stringify(m));
  await t.ctx.close();
}

// --- e) an AudioContext that never resumes (iOS) must not block recording ---
{
  const t = await openVoice({ hangResume: true });
  await t.touch('touchStart');
  await t.page.waitForTimeout(1500);
  check('e) with a hung resume(), the button still enters recording', /Speaking/.test(await t.label()));
  await t.page.waitForTimeout(2500);
  await t.touch('touchEnd');
  const got = await t.said.waitFor({ timeout: 6000 }).then(() => true, () => false);
  check('e) with a hung resume(), a 4s hold still produces a recording', got);
  await t.ctx.close();
}

// --- f) Space held down, auto-repeating ---
// The microphone takes 800ms to come up here, so the first dozen repeats
// land while the first start is still pending, which is when a second
// start would have opened a second stream.
{
  const t = await openVoice({ gumDelay: 800 });
  await t.button.focus();
  await t.page.keyboard.down('Space');
  for (let i = 0; i < 40; i++) {
    await t.page.waitForTimeout(i < 20 ? 40 : 150);
    await t.page.keyboard.down('Space'); // repeat: true
  }
  check('f) Space held: listening', /Speaking/.test(await t.label()));
  await t.page.keyboard.up('Space');
  const got = await t.said.waitFor({ timeout: 6000 }).then(() => true, () => false);
  check('f) releasing Space shows "What you said"', got);
  const m = await micState(t.page);
  check('f) key repeat opened exactly one stream and one recorder', m.gum === 1 && m.recorders === 1, JSON.stringify(m));
  check('f) the microphone is released', m.recordingNow === 0 && m.liveTracks === 0, JSON.stringify(m));
  await t.ctx.close();
}

// --- h) a second finger lands on the button and lifts mid-sentence ---
{
  const t = await openVoice();
  await t.fingers('touchStart', [[1, 0]]);
  await t.page.waitForTimeout(1500);
  await t.fingers('touchStart', [[1, 0], [2, 60]]);
  await t.page.waitForTimeout(300);
  // Chrome's touchEnd lifts the fingers it lists, whatever the protocol
  // docs say, so this lifts finger 2 alone.
  await t.fingers('touchEnd', [[2, 60]]);
  await t.page.waitForTimeout(500);
  check('h) the second finger lifting does not stop the first', /Speaking/.test(await t.label()));
  await t.page.waitForTimeout(1700);
  await t.fingers('touchEnd', [[1, 0]]);
  const got = await t.said.waitFor({ timeout: 6000 }).then(() => true, () => false);
  check('h) the first finger lifting produces the recording', got);
  await t.ctx.close();
}

// --- i) the screen goes away while the microphone is still opening ---
{
  const t = await openVoice({ gumDelay: 1500 });
  await t.touch('touchStart');
  await t.page.waitForTimeout(300);
  await t.page.getByRole('button', { name: 'Go back' }).tap();
  await t.page.waitForTimeout(2500);
  const m = await micState(t.page);
  check('i) leaving mid-start leaves no microphone open', m.recordingNow === 0 && m.liveTracks === 0, JSON.stringify(m));
  await t.touch('touchEnd');
  await t.ctx.close();
}

// --- g) ---
check('g) no page errors', errors.length === 0, errors.join(' | '));

await browser.close();
console.log(fails.length ? `\n${fails.length} failed` : '\nall passed');
process.exit(fails.length ? 1 : 0);
