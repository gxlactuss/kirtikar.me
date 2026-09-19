import { copy } from '../../copy/en';
import { dispatch, useDemo } from '../../machine/store';
import { BigActionButton } from '../widgets/BigActionButton';
import { Panel } from './Panel';
import { ReviewScaffold } from './ReviewScaffold';
import css from './review.module.css';

/**
 * "One question" — the server could not finish on its own.
 *
 * This is NOT a failure screen and is never badged as demo data. The
 * pipeline lands here when its vision gate rejects a photo or a fact is
 * missing, and `follow_up_question` carries the real reason. Showing it
 * verbatim is the point: it is the app being honest with the seller.
 */
export function NeedsAttentionStage() {
  const { listing } = useDemo();
  if (!listing) return null;

  return (
    <ReviewScaffold
      title={copy.attentionTitle}
      subtitle={copy.attentionBody}
      actions={
        <>
          <BigActionButton
            label="Carry on anyway"
            icon="arrow_forward"
            onClick={() => dispatch({ t: 'reviewNext' })}
          />
          <BigActionButton
            label={copy.attentionRetakePhotos}
            icon="photo_camera"
            tone="secondary"
            onClick={() => dispatch({ t: 'reset' })}
          />
        </>
      }
    >
      <Panel tone="danger">{listing.follow_up_question}</Panel>

      {listing.title ? (
        <div className={css.titleBlock}>
          <h2 className={css.listingTitle}>{listing.title}</h2>
          <p className={css.listingDesc}>{listing.description}</p>
        </div>
      ) : null}
    </ReviewScaffold>
  );
}
