import { useRef, useState } from 'react';

import { copy } from '../../copy/en';
import { PRODUCTS, PRODUCT_SLOTS, UPLOAD_SLUG, photoLabel, type Product } from '../products';
import { prepareFromUrl, prepareImage } from '../../util/image';
import { dispatch, useDemo } from '../../machine/store';
import type { Photo } from '../../machine/types';
import { BigActionButton } from '../widgets/BigActionButton';
import { Icon } from '../widgets/Icon';
import { Scaffold } from '../widgets/Scaffold';
import { ScreenHeader } from '../widgets/ScreenHeader';
import css from './capture.module.css';

/**
 * Step 1: exactly one photo, either the visitor's own or one of up to
 * twenty ready-made products. Picking another replaces it.
 *
 * This lives inside the phone rather than beside it so it works at every
 * width: below 1100px the stage hides its side column entirely.
 */
export function PickStage() {
  const { photo, error } = useDemo();
  // Which control is working, so only that one shows a spinner.
  const [busy, setBusy] = useState<'catalog' | 'upload' | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  function choose(next: Photo | null) {
    if (photo) URL.revokeObjectURL(photo.url);
    dispatch({ t: 'photo', photo: next });
  }

  async function pick(product: Product) {
    if (busy) return;
    if (photo?.slug === product.slug) return;
    setBusy('catalog');
    try {
      choose({ slug: product.slug, ...(await prepareFromUrl(product.image)) });
    } catch (e) {
      dispatch({ t: 'error', message: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  async function upload(file: File) {
    setBusy('upload');
    try {
      choose({ slug: UPLOAD_SLUG, ...(await prepareImage(file)) });
    } catch (e) {
      dispatch({
        t: 'error',
        message:
          e instanceof Error && /MB/.test(e.message) ? e.message : copy.demo.uploadUnreadable,
      });
    } finally {
      setBusy(null);
    }
  }

  // Empty slots are a note to whoever is filling the catalog, not something
  // a judge should ever see, so they only render in development.
  const empties = import.meta.env.DEV ? PRODUCT_SLOTS - PRODUCTS.length : 0;

  return (
    <Scaffold
      step={1}
      stepCount={3}
      actions={
        photo && !busy ? (
          <BigActionButton
            label={copy.demo.pickConfirm}
            icon="arrow_forward"
            onClick={() => dispatch({ t: 'goCapture', stage: 'voiceRecord' })}
          />
        ) : null
      }
    >
      <ScreenHeader
        title={copy.demo.pickTitle}
        subtitle={copy.demo.pickBody(PRODUCTS.length > 0)}
      />

      {photo ? (
        <figure className={css.chosen}>
          <img className={css.chosenImage} src={photo.url} alt={photoLabel(photo.slug)} />
          <figcaption className={css.chosenCaption}>
            <Icon name="check_circle" size={20} className={css.chosenTick} />
            {photoLabel(photo.slug)}
          </figcaption>
        </figure>
      ) : null}

      {error ? (
        <div className={css.error} role="alert">
          <Icon name="error_outline" size={22} className={css.errorIcon} />
          <span>{error}</span>
        </div>
      ) : null}

      <BigActionButton
        label={photo?.slug === UPLOAD_SLUG ? copy.demo.pickOwnAgain : copy.demo.pickOwn}
        icon="photo_camera"
        tone="secondary"
        busy={busy === 'upload'}
        disabled={busy === 'catalog'}
        onClick={() => fileInput.current?.click()}
      />
      <input
        ref={fileInput}
        className={css.sr}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        aria-label={copy.demo.pickOwn}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void upload(f);
          e.target.value = '';
        }}
      />

      {PRODUCTS.length || empties ? (
        <>
          <p className={css.sectionLabel}>{copy.demo.pickCatalog}</p>
          <div className={css.grid}>
            {PRODUCTS.map((product) => {
              const picked = photo?.slug === product.slug;
              return (
                <button
                  key={product.slug}
                  type="button"
                  className={css.tile}
                  data-product={product.slug}
                  aria-pressed={picked}
                  disabled={busy !== null}
                  onClick={() => void pick(product)}
                  title={product.label}
                >
                  <img src={product.image} alt="" loading="lazy" />
                  {picked ? (
                    <span className={css.tileTick}>
                      <Icon name="check" size={16} />
                    </span>
                  ) : null}
                  <span className={css.tileLabel}>{product.label}</span>
                </button>
              );
            })}
            {Array.from({ length: empties }, (_, i) => (
              <span
                key={`empty-${i}`}
                className={css.emptySlot}
                title="Add an image to src/assets/products/"
              >
                {PRODUCTS.length + i + 1}
              </span>
            ))}
          </div>
        </>
      ) : null}
    </Scaffold>
  );
}
