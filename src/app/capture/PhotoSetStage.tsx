import { copy } from '../../copy/en';
import { CRAFT_BY_SLUG, UPLOAD_SLUG } from '../crafts';
import { dispatch, useDemo } from '../../machine/store';
import { BigActionButton } from '../widgets/BigActionButton';
import { Icon } from '../widgets/Icon';
import { Scaffold } from '../widgets/Scaffold';
import { ScreenHeader } from '../widgets/ScreenHeader';
import css from './capture.module.css';

/**
 * "Your three photos" — the app's confirmation step before the voice note.
 *
 * On the phone this is where a seller retakes a bad shot. Here the photos
 * come from the rail, so the actions are remove-and-repick instead, but the
 * screen keeps the app's copy and the first-photo-is-special rule.
 */
export function PhotoSetStage() {
  const { photos } = useDemo();

  if (photos.length === 0) {
    return (
      <Scaffold>
        <ScreenHeader title={copy.demo.pickTitle} subtitle={copy.demo.pickBody} />
        <div className={css.empty}>
          <span className={css.emptyIcon}>
            <Icon name="image" size={38} />
          </span>
          <p className={css.emptyText}>
            Pick a product photo from the panel beside the phone, or upload one of
            your own.
          </p>
        </div>
      </Scaffold>
    );
  }

  const remove = (index: number) => {
    const photo = photos[index];
    if (photo) URL.revokeObjectURL(photo.url);
    dispatch({ t: 'photos', photos: photos.filter((_, i) => i !== index) });
  };

  return (
    <Scaffold
      step={1}
      stepCount={2}
      actions={
        <BigActionButton
          label={copy.photoSetConfirm}
          icon="check"
          onClick={() => dispatch({ t: 'goCapture', stage: 'voiceRecord' })}
        />
      }
    >
      <ScreenHeader title={copy.photoSetTitle} subtitle={copy.photoSetBody} />

      <div className={css.photoList}>
        {photos.map((photo, i) => {
          const name =
            photo.slug === UPLOAD_SLUG
              ? 'Your photo'
              : (CRAFT_BY_SLUG.get(photo.slug)?.label ?? photo.slug);
          return (
            <div className={css.photoRow} key={photo.url}>
              <img className={css.thumb} src={photo.url} alt={name} />
              <div className={css.photoMeta}>
                <span className={css.photoTitle}>
                  {i === 0 ? (
                    <>
                      <Icon name="star" size={20} className={css.star} />
                      {copy.photoSetMain}
                    </>
                  ) : (
                    name
                  )}
                </span>
                <span className={css.photoNote}>
                  {i === 0 ? name : `${photo.width} × ${photo.height}`}
                </span>
              </div>
              <button
                type="button"
                className={css.removeButton}
                onClick={() => remove(i)}
                aria-label={`Remove ${name}`}
              >
                <Icon name="close" size={24} />
              </button>
            </div>
          );
        })}
      </div>
    </Scaffold>
  );
}
