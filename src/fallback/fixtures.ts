import type { Listing } from '../api/types';
import type { StageId } from '../machine/types';

/**
 * A recorded run of the real pipeline against one of the bundled photos.
 *
 * Captured once by tools/capture-fixtures.mts against a live backend with
 * real API keys, so a fixture is not invented data — it is what the pipeline
 * actually produced for that image, replayed at its own measured pace.
 */
export interface Fixture {
  slug: string;
  /** ISO date the run was captured; shown to the visitor when one is used. */
  capturedAt: string;
  backendVersion: string;
  /** Wall-clock of the whole run, used to pace the replay. */
  pipelineMs: number;
  /** Per-stage timings from the backend's own logs, when available. */
  stageMs: Partial<Record<StageId, number>>;
  transcript: string | null;
  listing: Listing;
}

export interface FixtureIndexEntry {
  slug: string;
  path: string;
  title: string;
  state: Listing['state'];
}

const base = import.meta.env.BASE_URL;

let indexPromise: Promise<FixtureIndexEntry[]> | null = null;

/** Fixtures are fetched, not bundled — they must not bloat the entry chunk. */
export function fixtureIndex(): Promise<FixtureIndexEntry[]> {
  indexPromise ??= fetch(`${base}fixtures/index.json`)
    .then((r) => (r.ok ? (r.json() as Promise<FixtureIndexEntry[]>) : []))
    .catch(() => []);
  return indexPromise;
}

const cache = new Map<string, Promise<Fixture | null>>();

export function loadFixture(slug: string): Promise<Fixture | null> {
  let hit = cache.get(slug);
  if (!hit) {
    hit = fetch(`${base}fixtures/${slug}/listing.json`)
      .then(async (r) => {
        if (!r.ok) return null;
        const fixture = (await r.json()) as Fixture;
        return absolutise(fixture);
      })
      .catch(() => null);
    cache.set(slug, hit);
  }
  return hit;
}

/**
 * Picks the fixture recorded for this photo, or else a finished run.
 *
 * Most photos have no recording of their own (every upload, and any catalog
 * photo added since the last capture), so they borrow one. It borrows a
 * `ready` run on purpose: the point of the fallback is to show what a
 * finished product looks like. That is why the badge and the explainer say
 * a recorded run on a different photo, and why the fixture carries its own
 * images rather than reusing the visitor's.
 */
export async function pickFixture(slug: string | undefined): Promise<Fixture | null> {
  if (slug) {
    const hit = await loadFixture(slug);
    if (hit) return hit;
  }
  const index = await fixtureIndex();
  const pick = index.find((e) => e.state === 'ready') ?? index[0];
  return pick ? loadFixture(pick.slug) : null;
}

/** Rewrites relative image paths so they resolve under the site's base. */
function absolutise(fixture: Fixture): Fixture {
  return {
    ...fixture,
    listing: {
      ...fixture.listing,
      image_urls: fixture.listing.image_urls.map((u) =>
        u.startsWith('http') ? u : `${base}${u.replace(/^\/+/, '')}`,
      ),
    },
  };
}
