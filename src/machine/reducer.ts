import { afterPipeline } from './missing';
import type { Action, DemoState } from './types';
import { initialState } from './types';

export function reduce(s: DemoState, a: Action): DemoState {
  switch (a.t) {
    case 'photo':
      return { ...s, photo: a.photo, error: null };

    case 'goCapture':
      return { ...s, screen: { name: 'capture', stage: a.stage }, error: null };

    case 'voice':
      return { ...s, voice: a.voice, typed: null };

    case 'typed':
      return { ...s, typed: a.text, voice: null };

    case 'submit':
      return { ...s, screen: { name: 'processing' }, error: null };

    case 'progress':
      return { ...s, progress: a.progress };

    case 'queue':
      return { ...s, progress: { ...s.progress, queue: a.queue } };

    case 'listing':
      return {
        ...s,
        listing: a.listing,
        provenance: a.provenance,
        screen: { name: afterPipeline(a.listing) },
      };

    case 'answered':
      return { ...s, listing: a.listing, screen: { name: 'final' }, busy: false, error: null };

    case 'backend':
      return { ...s, backend: a.status };

    case 'busy':
      return { ...s, busy: a.busy };

    case 'error':
      return { ...s, error: a.message, busy: false };

    case 'reset':
      // Keep what we learned about the server; the visitor is starting a new
      // product, not reloading the page.
      return { ...initialState, backend: s.backend };
  }
}
