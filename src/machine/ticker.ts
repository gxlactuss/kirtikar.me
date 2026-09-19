import type { Progress, StageId } from './types';

/**
 * Drives the five-stage processing display.
 *
 * THE PROBLEM. The backend runs a five-stage pipeline
 * (services/pipeline/runner.py:31-39) but exposes only a listing `state` of
 * queued | processing | ready | needs_attention. There is no job id, no
 * per-stage feed, no SSE and no websocket. So the UI knows when the work
 * starts and when it ends, and nothing in between.
 *
 * THE RULES this class holds to, so the display is paced rather than faked:
 *
 *   1. Upload percentage is real bytes and never comes from here.
 *   2. The bar never reaches 100% until the server says the work is done.
 *   3. If the server finishes early, the remaining stages run out visibly
 *      instead of snapping to complete.
 *   4. If the server is slow, the last stage keeps breathing forever rather
 *      than freezing on a dead frame.
 *
 * Rules 2 and 4 are the same mechanism: the final stage is server-gated and
 * approaches completion asymptotically, so only finish() can end it.
 */

export interface StageSpec {
  id: StageId;
  label: string;
  nominalMs: number;
}

/** Measured against real runs; the sum is the 45s median. */
export const STAGES: readonly StageSpec[] = [
  { id: 'image', label: 'Cleaning up the photos', nominalMs: 9_000 },
  { id: 'speech', label: 'Listening to what you said', nominalMs: 7_000 },
  { id: 'fact_sheet', label: 'Writing it up', nominalMs: 22_000 },
  { id: 'price', label: 'Working out a fair price', nominalMs: 4_000 },
  { id: 'confidence', label: 'Checking it over', nominalMs: 3_000 },
];

export const SLOW_AFTER_MS = 75_000;
const MIN_SETTLE_MS = 1_100;
const MIN_PER_STAGE_MS = 240;
/** Ceiling on `overall` while the server has not confirmed. */
const CAP = 0.995;

type Clock = () => number;

export class PipelineTicker {
  private virtual = 0;
  private last = 0;
  private rate = 1;
  private serverDone = false;
  private running = false;
  private frame: number | null = null;

  constructor(
    private readonly emit: (p: Progress) => void,
    private stages: readonly StageSpec[] = STAGES,
    /** Injectable for tests; defaults to performance.now. */
    private readonly now: Clock = () => performance.now(),
    private readonly schedule: (cb: (t: number) => void) => number = (cb) =>
      requestAnimationFrame(cb),
    private readonly cancel: (h: number) => void = (h) => cancelAnimationFrame(h),
  ) {}

  get total(): number {
    return this.stages.reduce((n, s) => n + s.nominalMs, 0);
  }

  /**
   * Replace the stage timings before starting.
   *
   * A replayed fixture carries the per-stage durations its original run
   * actually took, so the progression is that run's real pacing rather than
   * the generic median. Refuses once the clock is moving, because retiming
   * mid-run would make the bar jump.
   */
  retime(stages: readonly StageSpec[]): void {
    if (this.running || this.virtual > 0) {
      throw new Error('retime() must be called before the ticker starts');
    }
    this.stages = stages;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.last = this.now();
    this.frame = this.schedule(this.loop);
  }

  /**
   * Called the moment a poll returns a terminal state, or the canned
   * fallback resolves. Releases the final stage and replays whatever is
   * left fast enough to feel like an ending but slow enough to be seen.
   */
  finish(): void {
    if (this.serverDone) return;
    this.serverDone = true;

    const snapshot = this.snapshot();
    const remaining = Math.max(0, this.total - this.virtual);
    const unfinished = this.stages.length - snapshot.done.filter(Boolean).length;
    const settleMs = Math.max(MIN_SETTLE_MS, unfinished * MIN_PER_STAGE_MS);

    this.rate = Math.max(1, remaining / settleMs);
    this.start();
  }

  stop(): void {
    this.running = false;
    if (this.frame !== null) {
      this.cancel(this.frame);
      this.frame = null;
    }
  }

  /** Advance the virtual clock by hand. Tests only. */
  advance(ms: number): Progress {
    this.virtual += ms * this.rate;
    return this.snapshot();
  }

  private loop = (): void => {
    if (!this.running) return;
    const t = this.now();
    this.virtual += (t - this.last) * this.rate;
    this.last = t;

    const progress = this.snapshot();
    this.emit(progress);

    if (progress.finished) {
      this.stop();
      return;
    }
    this.frame = this.schedule(this.loop);
  };

  snapshot(): Progress {
    let remaining = this.virtual;
    const done: boolean[] = [];
    let stageIndex = this.stages.length - 1;
    let stageProgress = 0;
    let elapsedOfDone = 0;

    for (let i = 0; i < this.stages.length; i++) {
      const stage = this.stages[i]!;
      const isLast = i === this.stages.length - 1;
      // The final stage may only complete once the server has confirmed.
      const mayComplete = !isLast || this.serverDone;

      if (remaining >= stage.nominalMs && mayComplete) {
        done.push(true);
        elapsedOfDone += stage.nominalMs;
        remaining -= stage.nominalMs;
        continue;
      }

      stageIndex = i;
      stageProgress = mayComplete
        ? Math.min(1, remaining / stage.nominalMs)
        : // Asymptote: ~0.80 at nominal, ~0.96 at twice nominal. Clamped at
          // 0.99 because the exponential saturates to exactly 1 in float64
          // after roughly 36x the time constant, which would read as "done"
          // and freeze the row. Liveness past this point is the shimmer on
          // the active row, not this number — a value that must strictly
          // increase forever is not representable anyway.
          Math.min(0.99, 1 - Math.exp(-remaining / (stage.nominalMs / 1.6)));

      while (done.length < this.stages.length) done.push(false);
      break;
    }

    const current = this.stages[stageIndex]!;
    const finished = done.every(Boolean);
    const raw = (elapsedOfDone + stageProgress * current.nominalMs) / this.total;
    const overall = finished ? 1 : Math.min(CAP, raw);

    return {
      queue: { kind: 'processing' },
      stageIndex,
      stageProgress,
      overall,
      done,
      finished,
      slow: !this.serverDone && this.virtual > SLOW_AFTER_MS,
    };
  }
}
