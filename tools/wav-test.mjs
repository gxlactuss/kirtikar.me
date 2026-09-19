// Verifies the WAV encoder in a real browser: synthesise tone -> encode to
// webm/opus via MediaRecorder -> run it through toWav() -> write to disk.
// Then `ffprobe`/`file` can confirm it is genuinely 22050 Hz mono PCM.
import { chromium } from 'playwright';
import { writeFileSync } from 'node:fs';

const browser = await chromium.launch({
  args: ['--autoplay-policy=no-user-gesture-required'],
});
const page = await browser.newPage();
page.on('console', (m) => console.log('  [browser]', m.text()));
page.on('pageerror', (e) => console.log('  [pageerror]', String(e)));

await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });

const result = await page.evaluate(async () => {
  const { toWav } = await import('/src/audio/wav.ts');

  // A 3-second 440 Hz tone at 48 kHz stereo, recorded through MediaRecorder
  // exactly as getUserMedia output would be.
  const ctx = new AudioContext({ sampleRate: 48000 });
  const dest = ctx.createMediaStreamDestination();
  const osc = ctx.createOscillator();
  osc.frequency.value = 440;
  osc.connect(dest);
  osc.start();

  const rec = new MediaRecorder(dest.stream);
  const chunks = [];
  rec.ondataavailable = (e) => chunks.push(e.data);
  rec.start();
  await new Promise((r) => setTimeout(r, 3000));
  const stopped = new Promise((r) => (rec.onstop = r));
  rec.stop();
  await stopped;
  osc.stop();

  const input = new Blob(chunks, { type: rec.mimeType });
  const { wav, seconds } = await toWav(input);
  const bytes = new Uint8Array(await wav.arrayBuffer());

  return {
    inputType: rec.mimeType,
    inputBytes: input.size,
    wavBytes: wav.size,
    seconds: Number(seconds.toFixed(3)),
    b64: btoa(String.fromCharCode(...bytes.slice(0, 64))),
    all: Array.from(bytes),
  };
});

console.log(`input:  ${result.inputType}  ${result.inputBytes} bytes`);
console.log(`output: audio/wav  ${result.wavBytes} bytes  ${result.seconds}s`);
writeFileSync('/tmp/kirtikar-tone.wav', Buffer.from(result.all));
console.log('wrote /tmp/kirtikar-tone.wav');

await browser.close();
