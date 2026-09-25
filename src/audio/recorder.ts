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

  constructor(private readonly events: RecorderEvents = {}) {}

  get recording(): boolean {
    return this.recorder?.state === 'recording';
  }

  async start(): Promise<void> {
    if (this.recording) return;
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

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (e) {
      const denied = e instanceof DOMException && e.name === 'NotAllowedError';
      throw new RecorderError(
        denied
          ? 'The microphone is blocked. Allow it in your browser and try again.'
          : 'The microphone did not start.',
        denied ? 'permission' : 'failed',
      );
    }

    this.chunks = [];
    this.peaks = [];
    this.level = 0;

    this.ctx = new AudioContext();
    // Chrome hands back a suspended context when one was created before any
    // gesture reached the page. A suspended context clocks no frames, so the
    // analyser reads pure silence and the waveform sits flat through the
    // whole recording even though the audio itself records fine.
    if (this.ctx.state === 'suspended') await this.ctx.resume();

    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 1024;
    this.ctx.createMediaStreamSource(this.stream).connect(this.analyser);

    this.recorder = new MediaRecorder(this.stream);
    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.recorder.start();
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
    void this.ctx?.close();
    this.ctx = null;
    this.analyser = null;
  }
}
