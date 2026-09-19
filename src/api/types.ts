/**
 * Wire types, mirroring the FastAPI schemas exactly.
 *
 * Source of truth: backend/app/schemas/listing.py. Keys are snake_case
 * because that is what the server sends; there is deliberately no camelCase
 * translation layer, so a field rename on either side shows up as a type
 * error rather than an undefined at runtime.
 *
 * Note the field is `state`, not `status` — the Flutter client aliases it,
 * the server does not.
 */

export type ListingState =
  | 'queued'
  | 'processing'
  | 'needs_attention'
  | 'ready'
  | 'published';

/** backend/app/services/listing.py:18-24 */
export const LEGAL_TRANSITIONS: Record<ListingState, readonly ListingState[]> = {
  queued: ['processing'],
  processing: ['needs_attention', 'ready'],
  needs_attention: ['processing', 'ready'],
  ready: ['published', 'needs_attention'],
  published: [],
};

export const TERMINAL_STATES: readonly ListingState[] = [
  'needs_attention',
  'ready',
  'published',
];

export interface FactSheet {
  material: string | null;
  size: string | null;
  colour: string | null;
  technique: string | null;
  origin: string | null;
  quantity: number | null;
  price_in_paise: number | null;
  hours_to_make: number | null;
  material_cost_in_paise: number | null;
  is_one_of_a_kind: boolean;
}

export interface Suggestion {
  id: string;
  field: string;
  spoken_prompt: string;
  text_if_accepted: string;
  approved: boolean | null;
}

export interface Listing {
  id: string;
  client_item_id: string;
  state: ListingState;
  title: string | null;
  description: string | null;
  image_urls: string[];
  fact_sheet: FactSheet;
  suggestions: Suggestion[];
  follow_up_question: string | null;
  suggested_price_in_paise: number | null;
  price_floor_in_paise: number | null;
  /** Always null from this server; the QR is built client-side instead. */
  preview_url: string | null;
  photo_consent: boolean;
  story_consent: boolean;
  views: number;
  /** false means the backend fell back to canned facts after Gemini failed. */
  used_live_model: boolean;
}

export interface ListingStatusResponse {
  listing_id: string;
  state: ListingState;
}

export interface MediaUploadResponse {
  id: string;
  listing_id: string;
  media_type: 'image' | 'audio';
  status: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

/**
 * The only fields PATCH /listings/{id} accepts.
 * backend/app/services/listing_fields.py:51-61 — anything else is a 400,
 * so this is a closed union rather than Record<string, unknown>.
 */
export type PatchableField =
  | 'material'
  | 'size'
  | 'colour'
  | 'technique'
  | 'origin'
  | 'quantity'
  | 'price'
  | 'isOneOfAKind';

export type ListingPatch = Partial<{
  material: string | null;
  size: string | null;
  colour: string | null;
  technique: string | null;
  origin: string | null;
  quantity: number | null;
  /** In paise, integer. Not rupees. */
  price: number | null;
  isOneOfAKind: boolean;
}>;

export const EMPTY_FACT_SHEET: FactSheet = {
  material: null,
  size: null,
  colour: null,
  technique: null,
  origin: null,
  quantity: null,
  price_in_paise: null,
  hours_to_make: null,
  material_cost_in_paise: null,
  is_one_of_a_kind: false,
};
