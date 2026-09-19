import { copy } from '../../copy/en';
import type { FactSheet, Listing } from '../../api/types';
import { rupees } from '../../util/money';
import css from './review.module.css';

interface Props {
  listing: Listing;
  priceInPaise: number | null;
  imageUrl: string | undefined;
}

const FACT_LABELS: [keyof FactSheet, string][] = [
  ['material', copy.fieldMaterial],
  ['size', copy.fieldSize],
  ['colour', copy.fieldColour],
  ['technique', copy.fieldTechnique],
  ['origin', copy.fieldOrigin],
];

/** What a buyer sees. Shared by the preview stage and the QR's buyer view. */
export function BuyerCard({ listing, priceInPaise, imageUrl }: Props) {
  const facts = FACT_LABELS.filter(([key]) => listing.fact_sheet[key] != null);

  return (
    <div className={css.buyerCard}>
      {imageUrl ? <img className={css.buyerImage} src={imageUrl} alt={listing.title ?? ''} /> : null}
      <div className={css.buyerBody}>
        <h2 className={css.buyerTitle}>{listing.title ?? 'Untitled'}</h2>
        <p className={css.buyerPrice}>
          {priceInPaise != null ? rupees(priceInPaise) : copy.listingNoPrice}
        </p>
        <p className={css.buyerDesc}>{listing.description}</p>

        {facts.length ? (
          <div className={css.buyerFacts}>
            {facts.map(([key, label]) => (
              <div key={key} style={{ display: 'contents' }}>
                <span className={css.buyerFactLabel}>{label}</span>
                <span className={css.buyerFactValue}>
                  {String(listing.fact_sheet[key])}
                </span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
