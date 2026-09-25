import type { FactSheet } from '../../api/types';
import { copy } from '../../copy/en';
import { dispatch, useDemo } from '../../machine/store';
import { rupees } from '../../util/money';
import { BigActionButton } from '../widgets/BigActionButton';
import { Scaffold } from '../widgets/Scaffold';
import { ScreenHeader } from '../widgets/ScreenHeader';
import { Panel } from './Panel';
import css from './result.module.css';

const FACTS: [keyof FactSheet, string][] = [
  ['material', copy.fieldMaterial],
  ['size', copy.fieldSize],
  ['colour', copy.fieldColour],
  ['technique', copy.fieldTechnique],
  ['origin', copy.fieldOrigin],
];

/**
 * Step 4: the finished product, as the pipeline wrote it plus whatever the
 * visitor typed in step 3. The image is the pipeline's processed one, not
 * the photo that was sent, so the clean-up stage shows its work too.
 */
export function FinalStage() {
  const { listing, provenance, photo } = useDemo();
  if (!listing) return null;

  const fs = listing.fact_sheet;
  const facts = FACTS.filter(([key]) => fs[key] != null && String(fs[key]).trim() !== '');

  // The backend fills the price with its own recommendation when none was
  // said; an unanswered "did not mention a price" flag is how to tell.
  const priceIsSuggestion = listing.suggestions.some(
    (s) => s.field === 'price' && s.approved === null,
  );

  const samePhoto = provenance?.kind === 'fixture' && provenance.slug === photo?.slug;
  const pill =
    provenance?.kind === 'fixture'
      ? copy.demo.demoDataPill
      : provenance?.kind === 'live' && !provenance.usedLiveModel
        ? copy.demo.offlineModelPill
        : null;

  return (
    <Scaffold
      pill={pill}
      actions={
        <BigActionButton
          label={copy.demo.finalAnother}
          icon="add"
          onClick={() => dispatch({ t: 'reset' })}
        />
      }
    >
      <ScreenHeader title={copy.demo.finalTitle} subtitle={copy.demo.finalBody} />

      {provenance?.kind === 'fixture' ? (
        <Panel>{copy.demo.demoDataExplain(formatDate(provenance.capturedAt), samePhoto)}</Panel>
      ) : null}
      {provenance?.kind === 'live' && !provenance.usedLiveModel ? (
        <Panel>{copy.demo.offlineModelExplain}</Panel>
      ) : null}

      <article className={css.card}>
        {listing.image_urls[0] ? (
          <img className={css.cardImage} src={listing.image_urls[0]} alt={listing.title ?? ''} />
        ) : null}
        <div className={css.cardBody}>
          <h2 className={css.cardTitle}>{listing.title}</h2>
          <p className={css.cardPrice}>
            {fs.price_in_paise != null ? rupees(fs.price_in_paise) : copy.listingNoPrice}
            {fs.price_in_paise != null && priceIsSuggestion ? (
              <span className={css.cardPriceNote}>{copy.demo.finalSuggestedPrice}</span>
            ) : null}
          </p>
          <p className={css.cardDesc}>{listing.description}</p>

          {facts.length ? (
            <dl className={css.facts}>
              {facts.map(([key, label]) => (
                <div key={key} style={{ display: 'contents' }}>
                  <dt>{label}</dt>
                  <dd>{String(fs[key])}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      </article>

      {listing.follow_up_question ? (
        <Panel icon="photo_camera">
          <span className={css.panelLabel}>{copy.demo.photoNote}</span>
          {listing.follow_up_question}
        </Panel>
      ) : null}
    </Scaffold>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}
