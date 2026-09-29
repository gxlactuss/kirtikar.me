import { toWav } from './wav';

/**
 * Microphone capture with a live level meter.
 *
 * Limits mirror the app (app/lib/core/constants/app_constants.dart:23-25):
 * 30 seconds hard cap with an auto-stop, 3 seconds minimum below which the
 * clip is rejected and the button re-armed.
 *
 * Level smoothing matches recorder_service.dart:132-139 — a -45 dBFS floor
 * and an exponential follower at 0.4 — so the waveform moves the way it does
 * on the phone rather than twitching on every frame.
 */

export const MAX_SECONDS = 30;
export const MIN_SECONDS = 3;
const DBFS_FLOOR = -45;
const SMOOTHING = 0.4;
const POLL_MS = 100;

const NO_SOUND =
  'No sound came through from the microphone. Check that this browser is allowed to use it ' +
  '(on a Mac: System Settings, Privacy & Security, Microphone), or type the description instead.';

export interface Recording {
  wav: Blob;
  seconds: number;
  peaks: number[];
}

/**
 * getUserMedia is gated on a secure context, so on plain http the whole
 * mediaDevices object is simply absent — indistinguishable, from the API
 * alone, from a browser too old to record. Checking isSecureContext first
 * lets the two be told apart, which matters because the advice differs:
 * one is fixed by opening https, the other is not fixed by anything.
 */
export function micBlockedReason(): 'insecure' | 'unsupported' | null {
  if (typeof window !== 'undefined' && !window.isSecureContext) return 'insecure';
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    return 'unsupported';
  }
  return null;
}

export type RecorderEvents = {
  onLevel?: (level: number, elapsedSeconds: number) => void;
  /** Fired when the 30s cap stops the recording on its own. */
  onLimit?: () => void;
};

export class RecorderError extends Error {
  constructor(
    message: string,
    readonly kind: 'permission' | 'unsupported' | 'insecure' | 'tooShort' | 'failed',
  ) {
    super(message);
    this.name = 'RecorderError';
  }
}

export class Recorder {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private timer: number | null = null;
  private chunks: Blob[] = [];
  private peaks: number[] = [];
  private level = 0;
  private startedAt = 0;
  private starting = false;
  private abandoned = false;

  constructor(private readonly events: RecorderEvents = {}) {}

  get recording(): boolean {
    return this.recorder?.state === 'recording';
  }

  /**
   * Must be called synchronously from the press itself (pointerdown or
   * keydown), because the meter's AudioContext is made before the first
   * await; see meterContext below.
   *
   * Resolves with `recording` still false when cancel() arrived while the
   * microphone was being opened; the stream is released by then.
   */
  async start(): Promise<void> {
    // A second start while the first is waiting on getUserMedia would open a
    // second stream, and only one of the two would ever be stopped.
    if (this.recording || this.starting) return;
    const blocked = micBlockedReason();
    if (blocked === 'insecure') {
      throw new RecorderError(
        'The microphone needs a secure connection. Open this page over https, or type the description instead.',
        'insecure',
      );
    }
    if (blocked === 'unsupported') {
      throw new RecorderError('This browser cannot record audio.', 'unsupported');
    }

    this.starting = true;
    this.abandoned = false;
    this.ctx = meterContext();

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (e) {
      this.starting = false;
      this.teardown();
      const denied = e instanceof DOMException && e.name === 'NotAllowedError';
      throw new RecorderError(
        denied
          ? 'The microphone is blocked. Allow it in your browser and try again.'
          : 'The microphone did not start.',
        denied ? 'permission' : 'failed',
      );
    }
    this.starting = false;

    // Let go before the microphone came up: on a phone the first press opens
    // the permission prompt, which cancels the touch, and a quick tap is over
    // before getUserMedia answers. Recording now would leave the microphone
    // running with no finger on the button and nothing left to stop it.
    if (this.abandoned) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    this.stream = stream;

    this.chunks = [];
    this.peaks = [];
    this.level = 0;

    // The meter is decoration; the recording below reads the stream directly
    // and must never wait on it or fail because of it.
    if (this.ctx) {
      try {
        // A second nudge now that capture is live: Safari is more lenient
        // with audio on a page that is capturing, so this can wake a context
        // the press could not. If it cannot, the waveform stays flat and the
        // recording is no worse for it.
        wake(this.ctx);
        this.analyser = this.ctx.createAnalyser();
        this.analyser.fftSize = 1024;
        this.ctx.createMediaStreamSource(stream).connect(this.analyser);
      } catch {
        this.analyser = null;
      }
    }

    try {
      this.recorder = new MediaRecorder(stream);
      this.recorder.ondataavailable = (e) => {
        if (e.data.size > 0) this.chunks.push(e.data);
      };
      this.recorder.start();
    } catch {
      // Without this the stream would stay open behind an error message,
      // with the browser's recording indicator still lit.
      this.teardown();
      throw new RecorderError('The microphone did not start.', 'failed');
    }
    this.startedAt = performance.now();

    this.timer = window.setInterval(() => this.tick(), POLL_MS);
  }

  /** Stops, converts to WAV, and enforces the 3-second minimum. */
  async stop(): Promise<Recording> {
    const rec = this.recorder;
    if (!rec || rec.state === 'inactive') {
      throw new RecorderError('Nothing was recorded.', 'failed');
    }

    const stopped = new Promise<void>((resolve) => {
      rec.onstop = () => resolve();
    });
    rec.stop();
    await stopped;
    this.teardown();

    // A microphone the OS has blocked, or one muted at the device, still
    // "records": getUserMedia succeeds and the timer runs, but what comes
    // back is empty or pure silence, and decoding it surfaces the browser's
    // own "Unable to decode audio data". Say what is actually wrong.
    const raw = new Blob(this.chunks, { type: rec.mimeType || 'audio/webm' });
    if (raw.size === 0) throw new RecorderError(NO_SOUND, 'failed');
    let converted: Awaited<ReturnType<typeof toWav>>;
    try {
      converted = await toWav(raw);
    } catch {
      throw new RecorderError(NO_SOUND, 'failed');
    }
    const { wav, seconds, silent } = converted;
    if (silent) throw new RecorderError(NO_SOUND, 'failed');

    if (seconds < MIN_SECONDS) {
      throw new RecorderError('That was very short.', 'tooShort');
    }
    return { wav, seconds, peaks: this.peaks.slice() };
  }

  /** Abandons the recording without producing anything. */
  cancel(): void {
    // If start() is still waiting on getUserMedia, this is what tells it to
    // hand the stream straight back instead of recording.
    this.abandoned = true;
    try {
      if (this.recorder?.state === 'recording') this.recorder.stop();
    } catch {
      /* already stopped */
    }
    this.teardown();
  }

  private tick(): void {
    const analyser = this.analyser;
    if (!analyser) return;

    const buf = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(buf);

    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i]! * buf[i]!;
    const rms = Math.sqrt(sum / buf.length);

    // dBFS, normalised against the floor, then smoothed.
    const db = 20 * Math.log10(Math.max(rms, 1e-7));
    const norm = Math.max(0, Math.min(1, (db - DBFS_FLOOR) / -DBFS_FLOOR));
    this.level += (norm - this.level) * SMOOTHING;
    this.peaks.push(this.level);

    const elapsed = (performance.now() - this.startedAt) / 1000;
    this.events.onLevel?.(this.level, elapsed);

    if (elapsed >= MAX_SECONDS) this.events.onLimit?.();
  }

  private teardown(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    void this.ctx?.close().catch(() => {});
    this.ctx = null;
    this.analyser = null;
  }
}

/**
 * The level meter's AudioContext, made inside the press.
 *
 * iOS Safari only lets a context start while a user gesture is being
 * handled. One made after `await getUserMedia` is outside it, stays
 * suspended, and `await ctx.resume()` on it can simply never settle, which
 * used to hang start() so the button never entered recording at all. Made
 * here, before the first await, it is still inside the pointerdown.
 *
 * Chrome likewise hands back a suspended context when no gesture has reached
 * the page, and a suspended context clocks no frames, so the analyser would
 * read pure silence and the waveform sit flat through the whole recording.
 *
 * Returns null rather than throwing: older iOS caps how many contexts a page
 * may hold, and a meter that cannot be built is no reason not to record.
 */
function meterContext(): AudioContext | null {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    wake(ctx);
    return ctx;
  } catch {
    return null;
  }
}

/**
 * Resume without waiting: a resume() that never settles must not matter.
 * Called whatever the state, because iOS also has a non-standard
 * "interrupted" state (the audio session switching to capture puts a running
 * context there), and resume() on a running context is a no-op anyway.
 */
function wake(ctx: AudioContext): void {
  ctx.resume().catch(() => {});
}
