import { copy } from '../../copy/en';
import { dispatch, useDemo } from '../../machine/store';
import { BigActionButton } from '../widgets/BigActionButton';
import { Icon } from '../widgets/Icon';
import { Panel } from './Panel';
import { ReviewScaffold } from './ReviewScaffold';
import css from './review.module.css';

/**
 * "May we put this up for sale?"
 *
 * Photo consent is required; story consent is genuinely optional and the
 * copy says so. The server echoes both back without persisting them
 * (record_listing_consent in listings.py:366-378 writes no row), so the
 * decision is enforced client-side for the preview and the QR payload.
 */
export function ConsentStage() {
  const { consent } = useDemo();

  return (
    <ReviewScaffold
      title={copy.consentTitle}
      actions={
        <BigActionButton
          label={copy.consentPublish}
          icon="check"
          disabled={!consent.photo}
          onClick={() => dispatch({ t: 'reviewGo', stage: 'publishing' })}
        />
      }
    >
      <Toggle
        on={consent.photo}
        label={copy.consentPhoto}
        explain={copy.consentPhotoExplain}
        onToggle={() => dispatch({ t: 'consent', photo: !consent.photo })}
      />
      <Toggle
        on={consent.story}
        label={copy.consentStory}
        explain={copy.consentStoryExplain}
        onToggle={() => dispatch({ t: 'consent', story: !consent.story })}
      />

      {!consent.photo ? <Panel tone="danger">{copy.consentNeeded}</Panel> : null}
    </ReviewScaffold>
  );
}

function Toggle({
  on,
  label,
  explain,
  onToggle,
}: {
  on: boolean;
  label: string;
  explain: string;
  onToggle: () => void;
}) {
  return (
    <button type="button" className={css.toggleRow} onClick={onToggle} aria-pressed={on}>
      <span className={`${css.checkbox} ${on ? css.checkboxOn : ''}`}>
        {on ? <Icon name="check" size={20} /> : null}
      </span>
      <span className={css.toggleBody}>
        <span className={css.toggleLabel}>{label}</span>
        <span className={css.toggleExplain}>{explain}</span>
      </span>
    </button>
  );
}
