import type { Listing, ListingState } from '../api/types';

/* ---------------- screens ---------------- */

export type CaptureStage = 'pickProduct' | 'photoSet' | 'voiceRecord' | 'typing' | 'saved';

/**
 * Order and skip rules ported from
 * app/lib/state/review_controller.dart:151-176.
 */
export type ReviewStage =
  | 'needsAttention'
  | 'readBack'
  | 'suggestions'
  | 'price'
  | 'stock'
  | 'photos'
  | 'preview'
  | 'consent'
  | 'publishing';

export type Screen =
  | { name: 'capture'; stage: CaptureStage }
  | { name: 'processing' }
  | { name: 'review'; stage: ReviewStage }
  | { name: 'published' };

export const REVIEW_ORDER: readonly ReviewStage[] = [
  'needsAttention',
  'readBack',
  'suggestions',
  'price',
  'stock',
  'photos',
  'preview',
  'consent',
  'publishing',
];

/**
 * The step bar counts the middle seven. `needsAttention` reports step 1 and
 * `publishing` has no step, exactly as the Dart does — and the total stays 7
 * even when `suggestions` is skipped, which is also what the Dart does.
 */
export const REVIEW_STEPS: readonly ReviewStage[] = REVIEW_ORDER.filter(
  (s) => s !== 'needsAttention' && s !== 'publishing',
);

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
  | 'network'
  | 'forced';

export type Provenance =
  | { kind: 'live'; usedLiveModel: boolean }
  | { kind: 'fixture'; reason: FallbackReason; slug: string; capturedAt: string };

export type BackendStatus = 'unknown' | 'warming' | 'live' | 'down';

/* ---------------- inputs ---------------- */

export interface Photo {
  /** Craft slug, or 'upload' for the visitor's own file. */
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
  photos: Photo[];
  voice: Voice | null;
  /** The "type it instead" fallback; mutually exclusive with `voice`. */
  typed: string | null;

  progress: Progress;
  listing: Listing | null;
  provenance: Provenance | null;
  backend: BackendStatus;

  /* review-local edits, applied optimistically then PATCHed */
  suggestionDecisions: Record<string, boolean>;
  priceInPaise: number | null;
  quantity: number;
  isOneOfAKind: boolean;
  photoOrder: number[];
  consent: { photo: boolean; story: boolean };

  busy: boolean;
  error: string | null;
}

export type Action =
  | { t: 'photos'; photos: Photo[] }
  | { t: 'goCapture'; stage: CaptureStage }
  | { t: 'voice'; voice: Voice }
  | { t: 'typed'; text: string }
  | { t: 'submit' }
  | { t: 'progress'; progress: Progress }
  | { t: 'queue'; queue: QueueState }
  | { t: 'listing'; listing: Listing; provenance: Provenance }
  | { t: 'listingState'; state: ListingState }
  | { t: 'reviewGo'; stage: ReviewStage }
  | { t: 'reviewNext' }
  | { t: 'reviewBack' }
  | { t: 'factField'; field: string; value: string | null }
  | { t: 'suggestion'; id: string; approved: boolean }
  | { t: 'price'; paise: number }
  | { t: 'quantity'; n: number }
  | { t: 'oneOfAKind'; value: boolean }
  | { t: 'photoOrder'; order: number[] }
  | { t: 'consent'; photo?: boolean; story?: boolean }
  | { t: 'backend'; status: BackendStatus }
  | { t: 'busy'; busy: boolean }
  | { t: 'error'; message: string | null }
  | { t: 'reset' };

export const initialState: DemoState = {
  screen: { name: 'capture', stage: 'pickProduct' },
  photos: [],
  voice: null,
  typed: null,
  progress: IDLE_PROGRESS,
  listing: null,
  provenance: null,
  backend: 'unknown',
  suggestionDecisions: {},
  priceInPaise: null,
  quantity: 1,
  isOneOfAKind: false,
  photoOrder: [],
  consent: { photo: true, story: true },
  busy: false,
  error: null,
};
