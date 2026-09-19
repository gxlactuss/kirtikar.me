/**
 * Records real pipeline runs and writes them to public/fixtures/.
 *
 * A fixture is not invented data: it is what the backend actually produced
 * for one of the bundled craft photos, replayed later at its own measured
 * pace. That is the whole basis on which the demo can claim a fallback run
 * shows the real pipeline, so this tool only ever writes what it received.
 *
 * Needs a live backend with working API keys:
 *
 *   API_BASE=http://localhost:8000 \
 *   node --experimental-strip-types tools/capture-fixtures.mts pottery weaving
 *
 * With no slugs it captures every craft in src/app/crafts.ts. Each run needs
 * a spoken sentence: supply one WAV per slug at fixtures-audio/<slug>.wav, or
 * pass --audio <file> to reuse a single recording for every capture. The
 * craft's own `hint` is what should be read aloud.
 */
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { basename, extname, join } from 'node:path';

import { CRAFTS } from '../src/app/crafts.ts';
import type { Listing, ListingStatusResponse } from '../src/api/types.ts';
import { TERMINAL_STATES } from '../src/api/types.ts';

const API_BASE = (process.env.API_BASE ?? 'http://localhost:8000').replace(/\/+$/, '');
const V1 = '/api/v1';
const OUT = 'public/fixtures';
const POLL_MS = 2_000;
const POLL_TIMEOUT_MS = 300_000;

const argv = process.argv.slice(2);
const audioFlag = argv.indexOf('--audio');
const sharedAudio = audioFlag === -1 ? null : argv[audioFlag + 1];
// Skip the flag's own value, but only when the flag is actually present —
// `audioFlag + 1` is 0 otherwise, which would silently eat the first slug.
const audioValueAt = audioFlag === -1 ? -1 : audioFlag + 1;
const slugs = argv.filter((a, i) => !a.startsWith('--') && i !== audioValueAt);

if (audioFlag !== -1 && !sharedAudio) {
  console.error('--audio needs a file path.');
  process.exit(1);
}

const unknown = slugs.filter((s) => !CRAFTS.some((c) => c.slug === s));
if (unknown.length) {
  console.error(`Unknown craft: ${unknown.join(', ')}`);
  console.error(`Known slugs: ${CRAFTS.map((c) => c.slug).join(', ')}`);
  process.exit(1);
}

const targets = slugs.length ? CRAFTS.filter((c) => slugs.includes(c.slug)) : [...CRAFTS];

interface IndexEntry {
  slug: string;
  path: string;
  title: string;
  state: Listing['state'];
}

async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body ? { 'content-type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    // Bare "fetch failed" says nothing about which host was unreachable.
    throw new Error(`cannot reach ${API_BASE} — set API_BASE? (${(error as Error).message})`);
  }
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

/** Resolves the WAV for one craft, preferring an explicit --audio. */
async function audioFor(slug: string): Promise<{ bytes: Buffer; name: string }> {
  const path = sharedAudio ?? join('fixtures-audio', `${slug}.wav`);
  if (!existsSync(path)) {
    throw new Error(
      `No audio for "${slug}". Record the craft's hint to ${path}, or pass --audio <file>.`,
    );
  }
  return { bytes: await readFile(path), name: basename(path) };
}

async function upload(listingId: string, bytes: Buffer, name: string, type: 'image' | 'audio') {
  const form = new FormData();
  form.append('file', new Blob([new Uint8Array(bytes)]), name);
  form.append('media_type', type);
  const res = await fetch(`${API_BASE}${V1}/listings/${listingId}/media`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error(`upload ${type} -> ${res.status} ${await res.text()}`);
}

/** Polls to a terminal state, returning how long the pipeline actually took. */
async function awaitPipeline(id: string): Promise<{ state: Listing['state']; ms: number }> {
  const startedAt = Date.now();
  for (;;) {
    const { state } = await api<ListingStatusResponse>('GET', `${V1}/listings/${id}/status`);
    if (TERMINAL_STATES.includes(state)) return { state, ms: Date.now() - startedAt };
    if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
      throw new Error(`still ${state} after ${Math.round(POLL_TIMEOUT_MS / 1000)}s`);
    }
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
}

/**
 * Pulls each generated image down beside the fixture.
 *
 * The replay has to render with the backend unreachable, so it cannot keep
 * pointing at /api/v1/.../media/... . Paths are stored relative to the site
 * root and re-absolutised at load time against BASE_URL.
 */
async function localiseImages(slug: string, listing: Listing): Promise<string[]> {
  const out: string[] = [];
  for (const [i, url] of listing.image_urls.entries()) {
    const absolute = url.startsWith('http') ? url : `${API_BASE}${url}`;
    const res = await fetch(absolute);
    if (!res.ok) {
      console.warn(`  ! image ${i + 1} -> ${res.status}, skipped`);
      continue;
    }
    const bytes = Buffer.from(await res.arrayBuffer());
    const ext = extname(new URL(absolute).pathname) || '.jpg';
    const name = `photo_${i + 1}${ext}`;
    await writeFile(join(OUT, slug, name), bytes);
    out.push(`fixtures/${slug}/${name}`);
    console.log(`  image ${i + 1}: ${bytes.length} bytes -> ${name}`);
  }
  return out;
}

async function capture(slug: string, hint: string): Promise<IndexEntry | null> {
  console.log(`\n=== ${slug} ===`);
  console.log(`  hint: ${hint}`);

  const photo = await readFile(join('public/crafts', `${slug}.jpg`));
  const audio = await audioFor(slug);

  const created = await api<Listing>('POST', `${V1}/listings`, {
    client_item_id: createHash('sha1').update(`${slug}:${Date.now()}`).digest('hex').slice(0, 32),
    photo_count: 1,
  });
  console.log(`  listing ${created.id}`);

  // Audio last: the server starts the pipeline once it has an image, an
  // audio file and the expected photo count.
  await upload(created.id, photo, `${slug}.jpg`, 'image');
  await upload(created.id, audio.bytes, audio.name, 'audio');

  const { state, ms } = await awaitPipeline(created.id);
  console.log(`  pipeline: ${state} in ${(ms / 1000).toFixed(1)}s`);

  const listing = await api<Listing>('GET', `${V1}/listings/${created.id}`);
  if (!listing.used_live_model) {
    console.warn('  ! used_live_model is false — the backend fell back to canned');
    console.warn('  ! facts. Recording this would bake a degraded run into the');
    console.warn('  ! demo, so it is skipped. Check the API keys and retry.');
    return null;
  }

  await mkdir(join(OUT, slug), { recursive: true });
  const imagePaths = await localiseImages(slug, listing);

  const health = await api<{ version: string }>('GET', '/health').catch(() => ({
    version: 'unknown',
  }));

  const fixture = {
    slug,
    capturedAt: new Date().toISOString().slice(0, 10),
    backendVersion: health.version,
    pipelineMs: ms,
    // The status endpoint reports a single state, not per-stage timings, so
    // these are left empty rather than invented; the ticker falls back to
    // its nominal pacing for any stage missing here.
    stageMs: {},
    transcript: null,
    listing: { ...listing, image_urls: imagePaths },
  };

  await writeFile(join(OUT, slug, 'listing.json'), `${JSON.stringify(fixture, null, 2)}\n`);
  console.log(`  wrote ${OUT}/${slug}/listing.json`);

  return { slug, path: `fixtures/${slug}/listing.json`, title: listing.title ?? slug, state: listing.state };
}

await mkdir(OUT, { recursive: true });

// Keep any fixture captured on an earlier run that is not being redone now.
const indexPath = join(OUT, 'index.json');
const existing: IndexEntry[] = existsSync(indexPath)
  ? JSON.parse(await readFile(indexPath, 'utf8'))
  : [];

const captured: IndexEntry[] = [];
for (const craft of targets) {
  try {
    const entry = await capture(craft.slug, craft.hint);
    if (entry) captured.push(entry);
  } catch (error) {
    console.error(`  FAILED ${craft.slug}: ${(error as Error).message}`);
  }
}

const merged = [
  ...existing.filter((e) => !captured.some((c) => c.slug === e.slug)),
  ...captured,
].sort((a, b) => a.slug.localeCompare(b.slug));

await writeFile(indexPath, `${JSON.stringify(merged, null, 2)}\n`);
console.log(`\n${captured.length}/${targets.length} captured; index lists ${merged.length}.`);
if (!captured.length) process.exitCode = 1;
