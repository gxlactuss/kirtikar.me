import { api } from './client';
import { dispatch } from '../machine/store';

/**
 * Watches whether the backend is reachable.
 *
 * A sleeping Hugging Face Space answers with an HTML "starting up" page and
 * takes 60-180s to come back, so the first failure is reported as `warming`
 * rather than `down` and retried. The client only gives up once the whole
 * window has elapsed — by which point the visitor is usually still choosing
 * a photo and never notices.
 */

const RETRY_MS = 5_000;
const WARMING_WINDOW_MS = 90_000;

export interface HealthWatcher {
  stop: () => void;
  /** Latency of the last successful check, in ms. */
  latency: () => number | null;
}

export function watchHealth(): HealthWatcher {
  let stopped = false;
  let timer: number | undefined;
  let latency: number | null = null;
  const startedAt = performance.now();

  const check = async () => {
    if (stopped) return;
    const t0 = performance.now();
    try {
      await api.health();
      latency = Math.round(performance.now() - t0);
      dispatch({ t: 'backend', status: 'live' });
      // Keep checking, but lazily: this only drives a status chip.
      timer = window.setTimeout(check, 30_000);
    } catch {
      if (stopped) return;
      const elapsed = performance.now() - startedAt;
      dispatch({ t: 'backend', status: elapsed > WARMING_WINDOW_MS ? 'down' : 'warming' });
      timer = window.setTimeout(check, RETRY_MS);
    }
  };

  void check();

  return {
    stop: () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    },
    latency: () => latency,
  };
}
