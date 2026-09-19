import type { Listing } from '../api/types';

/**
 * A self-contained buyer link.
 *
 * POST /publish returns `preview_url: null` unconditionally, so there is no
 * server-side page for a QR to point at. Encoding the listing into the URL
 * instead means the code scans on a judge's own phone, works while the
 * backend is asleep, and survives the Space restarting and dropping its
 * ephemeral database — which a listing-id link would not.
 */

export interface QrPayload {
  /** title */ t: string;
  /** description, truncated */ d: string;
  /** price in paise */ p: number | null;
  /** [label, value] pairs */ f: [string, string][];
  /** absolute image urls */ i: string[];
}

/**
 * Target length for the encoded URL.
 *
 * QR capacity is in bytes, and base64url encodes as byte mode. Roughly:
 * 600 bytes is a version-17 symbol (85 modules), 800 is version-21 (101).
 * Rendered at 240px that is 2.8px versus 2.4px per module — the difference
 * between a code that scans from across a table and one that needs the
 * phone held right against the screen.
 */
const MAX_URL_CHARS = 640;
const HARD_MAX_URL_CHARS = 900;
const DESC_FULL = 180;
const DESC_SHORT = 90;

/**
 * Marks a backend media reference stored as "~<listingId>/<mediaId>".
 *
 * A full media URL is ~145 characters, most of it the origin and the
 * /api/v1/listings/.../media/... path, which the buyer page already knows.
 * Storing just the two ids costs 74 and is the single biggest saving
 * available on the payload.
 */
const MEDIA_REF = '~';
const MEDIA_PATH = /\/api\/v1\/listings\/([^/]+)\/media\/([^/?]+)/;

export function buildPayload(
  listing: Listing,
  priceInPaise: number | null,
  imageUrls: string[],
  descLimit = DESC_FULL,
): QrPayload {
  const facts: [string, string][] = [];
  const add = (label: string, value: string | null) => {
    if (value) facts.push([label, value]);
  };
  add('Made of', listing.fact_sheet.material);
  add('Size', listing.fact_sheet.size);
  add('Colour', listing.fact_sheet.colour);
  add('How it was made', listing.fact_sheet.technique);
  add('Where it was made', listing.fact_sheet.origin);

  return {
    t: listing.title ?? 'Untitled',
    d: truncate(listing.description ?? '', descLimit),
    p: priceInPaise,
    f: facts,
    i: imageUrls.slice(0, 3).map(compactImage),
  };
}

/** "https://host/api/v1/listings/A/media/B?v=1" -> "~A/B" */
function compactImage(url: string): string {
  const match = MEDIA_PATH.exec(url);
  return match ? `${MEDIA_REF}${match[1]}/${match[2]}` : url;
}

/** Undoes compactImage. `apiBase` is where the media actually lives. */
export function expandImage(ref: string, apiBase: string): string {
  if (!ref.startsWith(MEDIA_REF)) return ref;
  const [listingId, mediaId] = ref.slice(1).split('/');
  return `${apiBase}/api/v1/listings/${listingId}/media/${mediaId}`;
}

/**
 * Builds the buyer URL, shrinking the payload if the QR would get too dense
 * to scan reliably from across a table.
 */
export function buyerUrl(
  origin: string,
  listing: Listing,
  priceInPaise: number | null,
  imageUrls: string[],
): string {
  let last = '';
  for (const limit of [DESC_FULL, DESC_SHORT, 0]) {
    last = `${origin}/?p=${encodePayload(buildPayload(listing, priceInPaise, imageUrls, limit))}`;
    if (last.length <= MAX_URL_CHARS) return last;
  }
  // Long titles and several images can still overshoot the comfortable
  // size. A denser code beats dropping the product photo, so accept it up
  // to the hard limit.
  if (last.length <= HARD_MAX_URL_CHARS) return last;

  // Beyond that the symbol stops being scannable, so fall back to a
  // fetch-on-open link. It needs the backend awake, which is why it is last.
  return `${origin}/?listing=${encodeURIComponent(listing.id)}`;
}

export function encodePayload(payload: QrPayload): string {
  return base64UrlEncode(new TextEncoder().encode(JSON.stringify(payload)));
}

export function decodePayload(encoded: string): QrPayload | null {
  try {
    const json = new TextDecoder().decode(base64UrlDecode(encoded));
    return normalise(JSON.parse(json));
  } catch {
    return null;
  }
}

/**
 * Anything can be pasted into a query string, so every field is checked
 * before the renderer sees it. A payload missing `f` used to throw on
 * `payload.f.length` and leave the buyer a blank page; now the field is
 * simply dropped and the rest of the product still shows.
 */
function normalise(value: unknown): QrPayload | null {
  if (typeof value !== 'object' || value === null) return null;
  const raw = value as Record<string, unknown>;
  if (typeof raw.t !== 'string') return null;

  const facts = Array.isArray(raw.f)
    ? raw.f.filter(
        (pair): pair is [string, string] =>
          Array.isArray(pair) &&
          typeof pair[0] === 'string' &&
          typeof pair[1] === 'string',
      )
    : [];

  return {
    t: raw.t,
    d: typeof raw.d === 'string' ? raw.d : '',
    p: typeof raw.p === 'number' && Number.isFinite(raw.p) ? raw.p : null,
    f: facts,
    i: Array.isArray(raw.i) ? raw.i.filter((u): u is string => typeof u === 'string') : [],
  };
}

function truncate(text: string, limit: number): string {
  if (limit === 0) return '';
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 1).trimEnd()}…`;
}

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = '';
  // Chunked: String.fromCharCode(...bytes) blows the argument limit on a
  // payload of any size.
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlDecode(encoded: string): Uint8Array {
  const padded = encoded.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4));
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}
