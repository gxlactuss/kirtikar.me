import { useEffect } from 'react';

import { copy } from '../../copy/en';
import { dispatch, useDemo } from '../../machine/store';
import { BigActionButton } from '../widgets/BigActionButton';
import { ReviewScaffold } from './ReviewScaffold';
import css from './review.module.css';

/**
 * "Which photo comes first?"
 *
 * The app reorders image_urls, but this backend's PATCH whitelist has no
 * imageUrls field (listing_fields.py:51-61 — sending it is a 400), so the
 * order is kept client-side and applied to the preview, the QR payload and
 * the buyer view. The seller's choice is honoured everywhere it is visible.
 */
export function PhotosStage() {
  const { listing, photoOrder } = useDemo();
  const urls = listing?.image_urls ?? [];
  const skip = urls.length <= 1;

  // Nothing to choose between: do not make the seller press through a screen
  // with one option on it. In an effect rather than during render, because
  // dispatching mid-render updates every other subscriber of the store
  // while React is still rendering this one.
  useEffect(() => {
    if (skip) dispatch({ t: 'reviewNext' });
  }, [skip]);

  if (!listing || skip) return null;

  const first = photoOrder[0] ?? 0;
  const choose = (index: number) =>
    dispatch({
      t: 'photoOrder',
      order: [index, ...urls.map((_, i) => i).filter((i) => i !== index)],
    });

  return (
    <ReviewScaffold
      title={copy.photosTitle}
      subtitle={copy.photoSetBody}
      actions={
        <BigActionButton
          label={copy.actionDone}
          icon="check"
          onClick={() => dispatch({ t: 'reviewNext' })}
        />
      }
    >
      <div className={css.photoGrid}>
        {urls.map((url, i) => (
          <button
            key={url}
            type="button"
            className={`${css.photoPick} ${i === first ? css.photoPickOn : ''}`}
            onClick={() => choose(i)}
            aria-pressed={i === first}
          >
            <img src={url} alt={`Photo ${i + 1}`} />
            {i === first ? <span className={css.photoBadge}>{copy.photoSetMain}</span> : null}
          </button>
        ))}
      </div>
    </ReviewScaffold>
  );
}
