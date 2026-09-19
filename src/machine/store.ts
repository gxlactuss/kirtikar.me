import { useSyncExternalStore } from 'react';

import { reduce } from './reducer';
import { type Action, type DemoState, initialState } from './types';

type Listener = () => void;

/**
 * A plain observable store, read through useSyncExternalStore.
 *
 * Deliberately not XState and not useReducer: the ticker in ./ticker.ts
 * emits on every animation frame, and keeping that outside React's render
 * cycle means a 60fps progress bar never re-runs the wizard's effects.
 * The reducer stays pure and testable in node with no DOM.
 */
export class DemoStore {
  private state: DemoState = initialState;
  private listeners = new Set<Listener>();

  getSnapshot = (): DemoState => this.state;

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  dispatch = (action: Action): void => {
    const next = reduce(this.state, action);
    if (next === this.state) return;
    this.state = next;
    for (const l of this.listeners) l();
  };

  /** Escape hatch for orchestration that needs the latest state mid-await. */
  peek = (): DemoState => this.state;
}

export const store = new DemoStore();

export function useDemo(): DemoState {
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}

export const dispatch = store.dispatch;
