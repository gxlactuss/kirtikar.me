import { copy } from '../../copy/en';
import type { FactSheet } from '../../api/types';
import { dispatch, useDemo } from '../../machine/store';
import { rupees } from '../../util/money';
import { BigActionButton } from '../widgets/BigActionButton';
import { FieldCard } from './FieldCard';
import { Panel } from './Panel';
import { ReviewScaffold } from './ReviewScaffold';
import css from './review.module.css';

/** The editable fields, in the app's order. Keys match FactSheet. */
const FIELDS: { key: keyof FactSheet; label: string }[] = [
  { key: 'material', label: copy.fieldMaterial },
  { key: 'size', label: copy.fieldSize },
  { key: 'colour', label: copy.fieldColour },
  { key: 'technique', label: copy.fieldTechnique },
  { key: 'origin', label: copy.fieldOrigin },
];

/**
 * "This is what we understood" — the seller checks the machine's work.
 *
 * Edits are applied locally straight away and PATCHed in the background, so
 * a slow network never blocks the wizard. The PATCH whitelist is enforced by
 * the type on ListingPatch.
 */
export function ReadBackStage() {
  const { listing, provenance } = useDemo();
  if (!listing) return null;

  return (
    <ReviewScaffold
      title={copy.readBackTitle}
      subtitle={copy.readBackCorrect}
      actions={
        <BigActionButton
          label={copy.readBackApprove}
          icon="check"
          onClick={() => dispatch({ t: 'reviewNext' })}
        />
      }
    >
      {provenance?.kind === 'fixture' ? (
        <Panel>{copy.demo.demoDataExplain(formatDate(provenance.capturedAt))}</Panel>
      ) : null}

      {provenance?.kind === 'live' && !provenance.usedLiveModel ? (
        <Panel>
          The photo and the voice note went through the real pipeline, but the
          writing model was unavailable, so the words below come from its offline
          fallback.
        </Panel>
      ) : null}

      <div className={css.titleBlock}>
        <h2 className={css.listingTitle}>{listing.title ?? 'Untitled'}</h2>
        <p className={css.listingDesc}>{listing.description}</p>
      </div>

      <p className={css.sectionLabel}>{copy.readBackFields}</p>

      <div className={css.fields}>
        {FIELDS.map(({ key, label }) => (
          <FieldCard
            key={key}
            label={label}
            value={(listing.fact_sheet[key] as string | null) ?? null}
            onSave={(value) => dispatch({ t: 'factField', field: key, value })}
          />
        ))}
        <FieldCard
          label={copy.fieldPrice}
          value={
            listing.fact_sheet.price_in_paise != null
              ? rupees(listing.fact_sheet.price_in_paise)
              : null
          }
          onSave={() => dispatch({ t: 'reviewGo', stage: 'price' })}
        />
      </div>
    </ReviewScaffold>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}
