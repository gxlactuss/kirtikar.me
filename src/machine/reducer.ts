import type { Action, DemoState, ReviewStage } from './types';
import { REVIEW_ORDER, REVIEW_STEPS, initialState } from './types';

/* ---------------- review stage navigation ---------------- */

/** The first pending suggestion, or null when there is nothing left to ask. */
export function pendingSuggestion(s: DemoState) {
  return (
    s.listing?.suggestions.find(
      (sug) => sug.approved === null && s.suggestionDecisions[sug.id] === undefined,
    ) ?? null
  );
}

const hasAttention = (s: DemoState) => Boolean(s.listing?.follow_up_question);

/**
 * Next stage, honouring the two skips from
 * review_controller.dart:191-193: `suggestions` is skipped when nothing is
 * pending, and `needsAttention` only appears when the server asked something.
 */
export function nextStage(s: DemoState, from: ReviewStage): ReviewStage | null {
  const i = REVIEW_ORDER.indexOf(from);
  if (i < 0 || i + 1 >= REVIEW_ORDER.length) return null;
  let next = REVIEW_ORDER[i + 1]!;
  if (next === 'suggestions' && pendingSuggestion(s) === null) next = 'price';
  return next;
}

export function prevStage(s: DemoState, from: ReviewStage): ReviewStage | null {
  const i = REVIEW_ORDER.indexOf(from);
  if (i <= 0) return null;
  let prev = REVIEW_ORDER[i - 1]!;
  if (prev === 'suggestions' && (s.listing?.suggestions.length ?? 0) === 0) {
    prev = 'readBack';
  }
  if (prev === 'needsAttention' && !hasAttention(s)) return null;
  return prev;
}

/**
 * 1-based step number for the bar. `needsAttention` reports 1 and
 * `publishing` reports 0 (hidden), matching the Dart.
 */
export function stepOf(stage: ReviewStage): number {
  if (stage === 'needsAttention') return 1;
  if (stage === 'publishing') return 0;
  return REVIEW_STEPS.indexOf(stage) + 1;
}

export const STEP_COUNT = REVIEW_STEPS.length; // 7

/** Where the wizard opens: the question first, if the server asked one. */
export function firstReviewStage(s: DemoState): ReviewStage {
  return hasAttention(s) ? 'needsAttention' : 'readBack';
}

/* ---------------- reducer ---------------- */

export function reduce(s: DemoState, a: Action): DemoState {
  switch (a.t) {
    case 'photos':
      return { ...s, photos: a.photos, photoOrder: a.photos.map((_, i) => i) };

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

    case 'listing': {
      const next: DemoState = {
        ...s,
        listing: a.listing,
        provenance: a.provenance,
        photoOrder: a.listing.image_urls.map((_, i) => i),
        // Seed the editable values from whatever the pipeline produced, so
        // the price and stock stages open on the server's suggestion rather
        // than on an empty field.
        priceInPaise:
          a.listing.fact_sheet.price_in_paise ?? a.listing.suggested_price_in_paise ?? null,
        quantity: a.listing.fact_sheet.quantity ?? 1,
        isOneOfAKind: a.listing.fact_sheet.is_one_of_a_kind,
      };
      return { ...next, screen: { name: 'review', stage: firstReviewStage(next) } };
    }

    case 'listingState':
      return s.listing ? { ...s, listing: { ...s.listing, state: a.state } } : s;

    case 'reviewGo':
      return { ...s, screen: { name: 'review', stage: a.stage }, error: null };

    case 'reviewNext': {
      if (s.screen.name !== 'review') return s;
      const next = nextStage(s, s.screen.stage);
      return next ? { ...s, screen: { name: 'review', stage: next }, error: null } : s;
    }

    case 'reviewBack': {
      if (s.screen.name !== 'review') return s;
      const prev = prevStage(s, s.screen.stage);
      return prev ? { ...s, screen: { name: 'review', stage: prev }, error: null } : s;
    }

    case 'factField': {
      if (!s.listing) return s;
      return {
        ...s,
        listing: {
          ...s.listing,
          fact_sheet: { ...s.listing.fact_sheet, [a.field]: a.value },
        },
      };
    }

    case 'suggestion':
      return {
        ...s,
        suggestionDecisions: { ...s.suggestionDecisions, [a.id]: a.approved },
      };

    case 'price':
      return { ...s, priceInPaise: a.paise };

    case 'quantity':
      return { ...s, quantity: Math.max(0, a.n) };

    case 'oneOfAKind':
      return { ...s, isOneOfAKind: a.value, quantity: a.value ? 1 : s.quantity };

    case 'photoOrder':
      return { ...s, photoOrder: a.order };

    case 'consent':
      return {
        ...s,
        consent: {
          photo: a.photo ?? s.consent.photo,
          story: a.story ?? s.consent.story,
        },
      };

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
