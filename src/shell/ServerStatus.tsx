import { useEffect, useRef, useState } from 'react';

import { API_BASE } from '../api/client';
import { watchHealth, type HealthWatcher } from '../api/health';
import { forceFixtures } from '../machine/flags';
import { useDemo } from '../machine/store';
import { toggleTheme, useTheme } from './theme';
import css from './ServerStatus.module.css';

const LABELS = {
  unknown: 'Checking the server…',
  warming: 'Waking the server…',
  live: 'Server live',
  down: 'Server unreachable',
} as const;

/**
 * Honest backend status, on every page.
 *
 * A judge can open this site on the opening logo, on the demo, or by
 * scanning the QR straight into a buyer page, and in all three they should
 * be able to tell at a glance whether what they are seeing came off the
 * network or out of a recording — without having to ask.
 *
 * It also owns the health watcher, which used to live beside the phone.
 * Mounting it at the root is what buys the backend its warm-up: a Space
 * that needs ninety seconds to wake starts waking on the first frame, while
 * the visitor is still looking at the logo.
 */
function Status() {
  const { backend, provenance } = useDemo();
  const [latency, setLatency] = useState<number | null>(null);
  const watcher = useRef<HealthWatcher | null>(null);

  useEffect(() => {
    // A forced demo never calls the backend, so polling it would only put a
    // red "unreachable" chip over a run that was never going to use it.
    if (forceFixtures()) return;
    watcher.current = watchHealth();
    const poll = setInterval(() => setLatency(watcher.current?.latency() ?? null), 1000);
    return () => {
      watcher.current?.stop();
      clearInterval(poll);
    };
  }, []);

  // Say so before the first run too, so the chip is never blank about why
  // nothing is being called.
  if (forceFixtures() && provenance?.kind !== 'fixture') {
    return (
      <span className={`${css.chip} ${css.warming}`} title="VITE_FORCE_FIXTURES or ?demo=1">
        <span className={css.dot} />
        Recorded run
      </span>
    );
  }

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

function ThemeToggle() {
  const theme = useTheme();
  const dark = theme === 'dark';

  return (
    <button
      type="button"
      className={css.toggle}
      onClick={toggleTheme}
      aria-pressed={dark}
      title={dark ? 'Switch to the light theme' : 'Switch to the dark theme'}
      aria-label={dark ? 'Switch to the light theme' : 'Switch to the dark theme'}
    >
      {dark ? (
        // Sun: what the button will give you, not what you have.
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <circle cx="12" cy="12" r="4.5" />
          <path
            strokeLinecap="round"
            d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M20.4 14.6A8.6 8.6 0 0 1 9.4 3.6a8.6 8.6 0 1 0 11 11Z" />
        </svg>
      )}
    </button>
  );
}

/** Server status and the theme switch, pinned above every page. */
export function ShellBar() {
  return (
    <div className={css.bar}>
      <Status />
      <ThemeToggle />
    </div>
  );
}
