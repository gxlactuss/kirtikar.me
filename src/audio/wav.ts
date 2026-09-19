/**
 * Re-encode a browser recording as 16-bit PCM mono WAV.
 *
 * WHY THIS EXISTS, in full, because it looks like pointless work:
 *
 * MediaRecorder gives us webm/opus on Chrome and mp4/AAC on Safari. The
 * backend's upload allowlist accepts both. But the Sarvam call in
 * backend/app/services/voice/pipeline.py:73-78 picks a Content-Type from the
 * file EXTENSION and falls through to "audio/wav" for anything it does not
 * recognise — including .webm. So an Opus stream would be posted to the STT
 * API labelled as WAV, and rejected.
 *
 * Converting here also collapses the Chrome/Safari difference into one
 * format, so there is a single code path to test.
 *
 * 22050 Hz mono matches the app's recorder (RecordConfig in
 * app/lib/services/recorder_service.dart:54-62), so the audio the server
 * receives from the web is the same shape it receives from a phone.
 */

export const TARGET_SAMPLE_RATE = 22050;

/** Decode whatever MediaRecorder produced, downmix, resample, encode WAV. */
export async function toWav(input: Blob): Promise<{ wav: Blob; seconds: number }> {
  const bytes = await input.arrayBuffer();

  // decodeAudioData handles webm/opus, mp4/AAC and ogg alike — it is the
  // browser's own demuxer, so we inherit whatever the platform supports.
  const decodeCtx = new (window.AudioContext || window.webkitAudioContext)();
  let decoded: AudioBuffer;
  try {
    decoded = await decodeCtx.decodeAudioData(bytes);
  } finally {
    void decodeCtx.close();
  }

  const mono = downmix(decoded);
  const resampled =
    decoded.sampleRate === TARGET_SAMPLE_RATE
      ? mono
      : await resample(mono, decoded.sampleRate, TARGET_SAMPLE_RATE);

  return {
    wav: encodeWav(resampled, TARGET_SAMPLE_RATE),
    seconds: resampled.length / TARGET_SAMPLE_RATE,
  };
}

/** Average all channels. A phone mic is mono anyway; this is for safety. */
function downmix(buffer: AudioBuffer): Float32Array<ArrayBuffer> {
  const { numberOfChannels, length } = buffer;
  // Copy into a fresh, definitely-not-shared buffer: copyToChannel and the
  // DataView encoder both require an ArrayBuffer, not an ArrayBufferLike.
  if (numberOfChannels === 1) return new Float32Array(buffer.getChannelData(0));

  const out = new Float32Array(length);
  for (let c = 0; c < numberOfChannels; c++) {
    const data = buffer.getChannelData(c);
    for (let i = 0; i < length; i++) out[i]! += data[i]!;
  }
  for (let i = 0; i < length; i++) out[i]! /= numberOfChannels;
  return out;
}

/**
 * Resample via OfflineAudioContext rather than by hand: it applies a proper
 * anti-aliasing filter, where naive index-picking would alias 48k speech
 * down to 22k and audibly hurt the transcript.
 */
async function resample(
  samples: Float32Array<ArrayBuffer>,
  from: number,
  to: number,
): Promise<Float32Array<ArrayBuffer>> {
  const frames = Math.max(1, Math.round((samples.length * to) / from));
  const ctx = new OfflineAudioContext(1, frames, to);

  const source = ctx.createBufferSource();
  const buffer = ctx.createBuffer(1, samples.length, from);
  buffer.copyToChannel(samples, 0);
  source.buffer = buffer;
  source.connect(ctx.destination);
  source.start();

  const rendered = await ctx.startRendering();
  return new Float32Array(rendered.getChannelData(0));
}

/** Canonical 44-byte RIFF header + signed 16-bit little-endian samples. */
export function encodeWav(samples: Float32Array<ArrayBuffer>, sampleRate: number): Blob {
  const bytesPerSample = 2;
  const blockAlign = bytesPerSample; // mono
  const dataBytes = samples.length * bytesPerSample;

  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);

  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  ascii(0, 'RIFF');
  view.setUint32(4, 36 + dataBytes, true);
  ascii(8, 'WAVE');

  ascii(12, 'fmt ');
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // format 1 = PCM
  view.setUint16(22, 1, true); // channels
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true); // byte rate
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true); // bits per sample

  ascii(36, 'data');
  view.setUint32(40, dataBytes, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    // Clamp before scaling: values outside [-1, 1] would wrap and click.
    const s = Math.max(-1, Math.min(1, samples[i]!));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}
