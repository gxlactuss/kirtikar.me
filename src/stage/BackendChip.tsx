import { useEffect, useRef, useState } from 'react';

import { watchHealth, type HealthWatcher } from '../api/health';
import { API_BASE } from '../api/client';
import { useDemo } from '../machine/store';
import css from './BackendChip.module.css';

const LABELS = {
  unknown: 'Checking the server…',
  warming: 'Waking the server…',
  live: 'Live',
  down: 'Server unreachable',
} as const;

/**
 * Honest status for the backend, always visible beside the phone.
 *
 * A judge should be able to tell at a glance whether what they are watching
 * came off the network or out of a recording, without having to ask.
 */
export function BackendChip() {
  const { backend, provenance } = useDemo();
  const [latency, setLatency] = useState<number | null>(null);
  const watcher = useRef<HealthWatcher | null>(null);

  useEffect(() => {
    watcher.current = watchHealth();
    const poll = setInterval(() => setLatency(watcher.current?.latency() ?? null), 1000);
    return () => {
      watcher.current?.stop();
      clearInterval(poll);
    };
  }, []);

  // Once a run has actually replayed a recording, that is the more useful
  // fact than whether the server is up.
  if (provenance?.kind === 'fixture') {
    return (
      <span className={`${css.chip} ${css.warming}`} title={`Fell back: ${provenance.reason}`}>
        <span className={css.dot} />
        Demo data
        <span className={css.meta}>{provenance.reason}</span>
      </span>
    );
  }

  return (
    <span className={`${css.chip} ${css[backend]}`} title={API_BASE}>
      <span className={css.dot} />
      {LABELS[backend]}
      {backend === 'live' && latency != null ? (
        <span className={css.meta}>{latency} ms</span>
      ) : null}
    </span>
  );
}
