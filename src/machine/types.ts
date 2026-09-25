import type { Listing } from '../api/types';

/* ---------------- screens ---------------- */

/**
 * The whole demo is four steps: pick one photo, speak about it, fill in
 * whatever the voice note left out, and see the finished product.
 */
export type CaptureStage = 'pick' | 'voiceRecord' | 'typing';

export type Screen =
  | { name: 'capture'; stage: CaptureStage }
  | { name: 'processing' }
  | { name: 'missing' }
  | { name: 'final' };

/* ---------------- transport ---------------- */

export type QueueState =
  | { kind: 'idle' }
  | { kind: 'waiting' }
  | { kind: 'uploading'; percent: number }
  | { kind: 'processing' }
  | { kind: 'failed'; message: string };

/** The backend's real pipeline stages (services/pipeline/runner.py:31-39). */
export type StageId = 'image' | 'speech' | 'fact_sheet' | 'price' | 'confidence';

export interface Progress {
  queue: QueueState;
  /** Which of the five stages is running. */
  stageIndex: number;
  /** 0..1 within the current stage. */
  stageProgress: number;
  /** 0..1 overall, capped below 1 until the server confirms. */
  overall: number;
  done: boolean[];
  finished: boolean;
  /** Past the reassurance threshold with no answer yet. */
  slow: boolean;
}

export const IDLE_PROGRESS: Progress = {
  queue: { kind: 'idle' },
  stageIndex: 0,
  stageProgress: 0,
  overall: 0,
  done: [false, false, false, false, false],
  finished: false,
  slow: false,
};

/* ---------------- provenance ---------------- */

export type FallbackReason =
  | 'cold-start'
  | 'create-failed'
  | 'upload-failed'
  | 'poll-timeout'
  | 'server-error'
  | 'daily-limit'
  | 'network'
  | 'forced';

export type Provenance =
  | { kind: 'live'; usedLiveModel: boolean }
  | { kind: 'fixture'; reason: FallbackReason; slug: string; capturedAt: string };

export type BackendStatus = 'unknown' | 'warming' | 'live' | 'down';

/* ---------------- inputs ---------------- */

export interface Photo {
  /** Catalog slug, or 'upload' for the visitor's own file. */
  slug: string;
  blob: Blob;
  url: string;
  width: number;
  height: number;
}

export interface Voice {
  /** 16-bit PCM mono WAV, ready to upload. */
  wav: Blob;
  seconds: number;
  /** Normalised levels captured while recording, for the playback waveform. */
  peaks: number[];
  url: string;
}

/* ---------------- the whole thing ---------------- */

export interface DemoState {
  screen: Screen;
  /** Exactly one photo once chosen; null before. */
  photo: Photo | null;
  voice: Voice | null;
  /** The "type it instead" fallback; mutually exclusive with `voice`. */
  typed: string | null;

  progress: Progress;
  listing: Listing | null;
  provenance: Provenance | null;
  backend: BackendStatus;

  busy: boolean;
  error: string | null;
}

export type Action =
  | { t: 'photo'; photo: Photo | null }
  | { t: 'goCapture'; stage: CaptureStage }
  | { t: 'voice'; voice: Voice }
  | { t: 'typed'; text: string }
  | { t: 'submit' }
  | { t: 'progress'; progress: Progress }
  | { t: 'queue'; queue: QueueState }
  | { t: 'listing'; listing: Listing; provenance: Provenance }
  | { t: 'answered'; listing: Listing }
  | { t: 'backend'; status: BackendStatus }
  | { t: 'busy'; busy: boolean }
  | { t: 'error'; message: string | null }
  | { t: 'reset' };

export const initialState: DemoState = {
  screen: { name: 'capture', stage: 'pick' },
  photo: null,
  voice: null,
  typed: null,
  progress: IDLE_PROGRESS,
  listing: null,
  provenance: null,
  backend: 'unknown',
  busy: false,
  error: null,
};
