import { useSyncExternalStore } from 'react';

/**
 * Light or dark for the stage around the phone.
 *
 * Light is the default and the honest one: it is the app's own cream, so
 * the demo page and the product inside the frame read as one thing. Dark is
 * there because the site is shown on projectors and in dim rooms, and a
 * full-screen cream wall is hard on the eyes there.
 *
 * Deliberately not a React context. The attribute lives on <html>, which is
 * above the React root, and every surface is painted from CSS variables —
 * so the switch is one attribute write and no component re-renders to
 * recolour itself.
 */

export type Theme = 'light' | 'dark';

const KEY = 'kirtikar:theme';

const listeners = new Set<() => void>();
let current: Theme = read();

function read(): Theme {
  try {
    return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    // Private windows and locked-down browsers throw rather than return null.
    return 'light';
  }
}

/** Applied before first paint so the page never flashes the wrong theme. */
export function applyTheme(theme: Theme = current): void {
  current = theme;
  document.documentElement.dataset.theme = theme;
}

export function toggleTheme(): void {
  const next: Theme = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  try {
    localStorage.setItem(KEY, next);
  } catch {
    // The theme still applies for this visit; it just will not be remembered.
  }
  for (const l of listeners) l();
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => current,
    () => current,
  );
}
