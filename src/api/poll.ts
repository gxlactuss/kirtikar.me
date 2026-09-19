import type { ApiClient } from './client';
import { HttpError } from './errors';
import type { Listing } from './types';
import type { FallbackReason } from '../machine/types';

/** Matches the app's watcher: 3s, backing off toward 30s. */
const BASE_MS = 3_000;
const FACTOR = 1.35;
const MAX_MS = 30_000;
const JITTER = 0.15;

/**
 * 45s nominal + the server's 90s Gemini budget + slack. Past this the run is
 * treated as lost and the fallback takes over, which is also why the demo
 * Space sets PIPELINE_MAX_STAGE_ATTEMPTS=2 — three attempts at a 90s
 * timeout could outlast this by minutes.
 */
const BUDGET_MS = 150_000;
const MAX_CONSECUTIVE_5XX = 3;

export type PollOutcome =
  | { ok: true; listing: Listing }
  | { ok: false; reason: FallbackReason };

const jitter = (ms: number) => ms * (1 + (Math.random() * 2 - 1) * JITTER);

/**
 * Sleep that also wakes when the tab becomes visible.
 *
 * Browsers throttle timers in background tabs, so a judge who switches away
 * mid-run and comes back would otherwise sit staring at a stale screen until
 * a 30-second timer eventually fired.
 */
function sleepOrWake(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const finish = () => {
      clearTimeout(timer);
      detach();
      resolve();
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') finish();
    };
    const onAbort = () => {
      clearTimeout(timer);
      detach();
      reject(new DOMException('Aborted', 'AbortError'));
    };
    const detach = () => {
      document.removeEventListener('visibilitychange', onVisible);
      signal.removeEventListener('abort', onAbort);
    };

    const timer = setTimeout(finish, ms);
    document.addEventListener('visibilitychange', onVisible);
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

/**
 * Polls /status until the listing reaches a terminal state, then fetches it
 * once in full.
 *
 * `needs_attention` counts as success, not failure: it is a real app state
 * with its own screen, carrying the server's question in
 * `follow_up_question`.
 */
export async function pollToTerminal(
  api: ApiClient,
  id: string,
  signal: AbortSignal,
): Promise<PollOutcome> {
  const startedAt = performance.now();
  let delay = 0; // first poll fires immediately
  let consecutive5xx = 0;

  for (;;) {
    if (delay > 0) await sleepOrWake(jitter(delay), signal);
    if (performance.now() - startedAt > BUDGET_MS) {
      return { ok: false, reason: 'poll-timeout' };
    }

    try {
      const { state } = await api.status(id, signal);
      consecutive5xx = 0;

      if (state === 'ready' || state === 'needs_attention' || state === 'published') {
        return { ok: true, listing: await api.listing(id, signal) };
      }
    } catch (e) {
      if (signal.aborted) throw e;

      if (e instanceof HttpError) {
        // A 404 means the listing is gone — the Space restarted and took its
        // ephemeral database with it. Nothing to wait for.
        if (e.status === 404) return { ok: false, reason: 'server-error' };
        if (e.status >= 500 && ++consecutive5xx >= MAX_CONSECUTIVE_5XX) {
          return { ok: false, reason: 'server-error' };
        }
      }
      // Network blips do not count against the run: the Space may still be
      // waking, and the wall-clock budget already bounds the wait.
    }

    delay = delay === 0 ? BASE_MS : Math.min(MAX_MS, delay * FACTOR);
  }
}
