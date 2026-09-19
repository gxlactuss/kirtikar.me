import { useRef, useState } from 'react';

import { CRAFTS, UPLOAD_SLUG, craftImage } from '../app/crafts';
import { prepareFromUrl, prepareImage } from '../util/image';
import { dispatch, useDemo } from '../machine/store';
import type { Photo } from '../machine/types';
import css from './ProductRail.module.css';

export const MAX_PHOTOS = 3;

/**
 * The picker outside the phone.
 *
 * Choosing 1-3 photos rather than always 3: the app takes three shots of one
 * object, but a judge picking three different crafts would confuse the
 * pipeline. One is enough to run, three shows the multi-photo path, and the
 * count is passed to the server as photo_count so it knows when to start.
 */
export function ProductRail() {
  const { photos, screen } = useDemo();
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // Locked once the run starts; changing the inputs mid-pipeline would make
  // the progression describe something other than what was sent.
  const locked = screen.name !== 'capture';

  const indexOfSlug = (slug: string) => photos.findIndex((p) => p.slug === slug);

  async function toggle(slug: string) {
    if (locked || busy) return;
    const at = indexOfSlug(slug);

    if (at >= 0) {
      const removed = photos[at]!;
      URL.revokeObjectURL(removed.url);
      dispatch({ t: 'photos', photos: photos.filter((_, i) => i !== at) });
      return;
    }
    if (photos.length >= MAX_PHOTOS) return;

    setBusy(true);
    try {
      const prepared = await prepareFromUrl(craftImage(slug));
      const photo: Photo = { slug, ...prepared };
      dispatch({ t: 'photos', photos: [...photos, photo] });
    } catch (e) {
      dispatch({ t: 'error', message: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(file: File) {
    if (photos.length >= MAX_PHOTOS) return;
    setBusy(true);
    try {
      const prepared = await prepareImage(file);
      dispatch({ t: 'photos', photos: [...photos, { slug: UPLOAD_SLUG, ...prepared }] });
    } catch (e) {
      dispatch({ t: 'error', message: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={css.root}>
      <p className={css.title}>Product photo</p>
      <p className={css.hint}>
        Pick up to {MAX_PHOTOS}, or upload your own. These go to the real pipeline.
      </p>

      <div className={css.grid}>
        {CRAFTS.map((craft) => {
          const at = indexOfSlug(craft.slug);
          const picked = at >= 0;
          return (
            <button
              key={craft.slug}
              type="button"
              className={css.tile}
              aria-pressed={picked}
              disabled={locked || (!picked && photos.length >= MAX_PHOTOS)}
              onClick={() => toggle(craft.slug)}
              title={craft.label}
            >
              <img src={craftImage(craft.slug)} alt={craft.label} loading="lazy" />
              {picked ? <span className={css.order}>{at + 1}</span> : null}
              <span className={css.tileLabel}>{craft.label}</span>
            </button>
          );
        })}

        <button
          type="button"
          className={css.uploadTile}
          disabled={locked || photos.length >= MAX_PHOTOS}
          onClick={() => fileInput.current?.click()}
        >
          <span aria-hidden="true" style={{ fontSize: 15, lineHeight: 1 }}>
            +
          </span>
          <span>Upload</span>
        </button>
      </div>

      <input
        ref={fileInput}
        className={css.sr}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void onUpload(f);
          e.target.value = '';
        }}
      />

      {busy ? <p className={css.busy}>Preparing…</p> : null}

      <p className={css.attribution}>
        Photographs from Wikimedia Commons —{' '}
        <a href={`${import.meta.env.BASE_URL}crafts/ATTRIBUTION.md`} target="_blank" rel="noreferrer">
          licences and credits
        </a>
      </p>
    </div>
  );
}
