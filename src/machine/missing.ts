import type { Listing, ListingPatch } from '../api/types';

/**
 * The fields the "a few things are missing" step can ask about.
 *
 * Every one is a field PATCH /listings/{id} accepts
 * (backend/app/services/listing_fields.py), so an answer is stored on the
 * real listing rather than only on screen. Time taken and material cost are
 * in the voice guide but not here: the pipeline never extracts them, so
 * asking would mean asking every time, even when the visitor said them.
 */
export type AskField = 'material' | 'size' | 'colour' | 'origin' | 'price';

export const ASK_ORDER: readonly AskField[] = ['material', 'size', 'colour', 'origin', 'price'];

/** Fields that count as missing whenever the fact sheet has nothing there. */
const CORE: readonly AskField[] = ['material', 'size', 'colour', 'price'];

/**
 * A run that stopped before it wrote anything (the voice note could not be
 * heard, say) has no product to finish. Typed answers cannot rescue it.
 */
export function isHalted(listing: Listing): boolean {
  return !listing.title;
}

/**
 * What to ask for, in a stable order.
 *
 * A field is asked when the server flagged it as not said (a pending
 * suggestion), or when it is one of the core facts and came back empty.
 * Price needs the flag: when the visitor names none, the backend fills
 * `price_in_paise` with its own recommendation, so the value alone would
 * hide that the visitor never said one.
 */
export function missingFields(listing: Listing): AskField[] {
  if (isHalted(listing)) return [];

  const flagged = new Set(
    listing.suggestions.filter((s) => s.approved === null).map((s) => s.field),
  );
  const fs = listing.fact_sheet;
  const empty = (f: AskField) =>
    f === 'price' ? fs.price_in_paise == null : !fs[f]?.trim();

  return ASK_ORDER.filter((f) => flagged.has(f) || (CORE.includes(f) && empty(f)));
}

/** Where the run goes once the pipeline answers. */
export function afterPipeline(listing: Listing): 'missing' | 'final' {
  return isHalted(listing) || missingFields(listing).length > 0 ? 'missing' : 'final';
}

/**
 * "1,200", "₹1200", "Rs. 1200.50" -> paise. Null when it is not a positive
 * amount, so a stray word never becomes a price of zero.
 */
export function rupeesToPaise(text: string): number | null {
  const cleaned = text.replace(/₹|rs\.?|inr|rupees?|,|\s/gi, '');
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const paise = Math.round(Number(cleaned) * 100);
  return paise > 0 ? paise : null;
}

export type Answers = Partial<Record<AskField, string>>;

/**
 * Turns the typed answers into a PATCH body. Blank answers are left out, so
 * skipping a field keeps whatever the pipeline had rather than erasing it.
 */
export function answersToPatch(answers: Answers): ListingPatch {
  const patch: ListingPatch = {};
  for (const field of ASK_ORDER) {
    const raw = answers[field]?.trim();
    if (!raw) continue;
    if (field === 'price') {
      const paise = rupeesToPaise(raw);
      if (paise != null) patch.price = paise;
    } else {
      patch[field] = raw;
    }
  }
  return patch;
}

/**
 * Applies a PATCH to a listing the way the server does, for a recorded run
 * that has no server-side listing to send it to. Answering a field also
 * settles the suggestion about it (listing_fields.settle_suggestion_for_field).
 */
export function applyLocally(listing: Listing, patch: ListingPatch): Listing {
  const { price, ...text } = patch;
  const answered = new Set<string>(Object.keys(patch));
  return {
    ...listing,
    fact_sheet: {
      ...listing.fact_sheet,
      ...text,
      ...(price != null ? { price_in_paise: price } : {}),
    },
    suggestions: listing.suggestions.map((s) =>
      answered.has(s.field) && s.approved === null ? { ...s, approved: true } : s,
    ),
  };
}
