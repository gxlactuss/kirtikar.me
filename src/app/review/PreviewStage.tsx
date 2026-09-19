import { copy } from '../../copy/en';
import { dispatch, useDemo } from '../../machine/store';
import { BigActionButton } from '../widgets/BigActionButton';
import { BuyerCard } from './BuyerCard';
import { ReviewScaffold } from './ReviewScaffold';

/** "This is what buyers will see." */
export function PreviewStage() {
  const { listing, priceInPaise, photoOrder } = useDemo();
  if (!listing) return null;

  const firstIndex = photoOrder[0] ?? 0;

  return (
    <ReviewScaffold
      title={copy.previewTitle}
      actions={
        <BigActionButton
          label={copy.actionDone}
          icon="arrow_forward"
          onClick={() => dispatch({ t: 'reviewNext' })}
        />
      }
    >
      <BuyerCard
        listing={listing}
        priceInPaise={priceInPaise}
        imageUrl={listing.image_urls[firstIndex]}
      />
    </ReviewScaffold>
  );
}
