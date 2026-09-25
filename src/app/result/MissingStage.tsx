import { useState } from 'react';

import { api } from '../../api/client';
import { copy } from '../../copy/en';
import {
  answersToPatch,
  applyLocally,
  isHalted,
  missingFields,
  rupeesToPaise,
  type Answers,
  type AskField,
} from '../../machine/missing';
import { withAbsoluteImages } from '../../machine/run';
import { dispatch, useDemo } from '../../machine/store';
import { rupees } from '../../util/money';
import { BigActionButton } from '../widgets/BigActionButton';
import { Scaffold } from '../widgets/Scaffold';
import { ScreenHeader } from '../widgets/ScreenHeader';
import { Panel } from './Panel';
import css from './result.module.css';

const QUESTION: Record<AskField, { label: string; hint?: string }> = {
  material: { label: copy.demo.missingMaterial },
  size: { label: copy.demo.missingSize, hint: copy.demo.missingSizeHint },
  colour: { label: copy.demo.missingColour },
  origin: { label: copy.demo.missingOrigin, hint: copy.demo.missingOriginHint },
  price: { label: copy.priceTitle },
};

/**
 * Step 3: whatever the voice note left out, asked for in writing.
 *
 * Text only, on purpose: the one voice note is the whole spoken input, and
 * a second recording here would blur which words the listing came from.
 * Answers are PATCHed onto the real listing, the same call the app makes
 * when a seller corrects a field, which also settles the server's
 * "did not mention" suggestion for that field.
 */
export function MissingStage() {
  const { listing, provenance, photo, busy, error } = useDemo();
  const [answers, setAnswers] = useState<Answers>({});
  const [touchedPrice, setTouchedPrice] = useState(false);

  if (!listing) return null;

  if (isHalted(listing)) {
    return (
      <Scaffold
        actions={
          <BigActionButton
            label={copy.attentionStartAgain}
            icon="refresh"
            onClick={() => dispatch({ t: 'reset' })}
          />
        }
      >
        <ScreenHeader title={copy.demo.haltedTitle} />
        <Panel tone="danger">
          {listing.follow_up_question ?? copy.demo.processingFailedTitle}
        </Panel>
      </Scaffold>
    );
  }

  const fields = missingFields(listing);
  const why = new Map(listing.suggestions.map((s) => [s.field, s.spoken_prompt]));

  const priceText = answers.price?.trim() ?? '';
  const priceInvalid = priceText !== '' && rupeesToPaise(priceText) == null;

  async function submit() {
    if (!listing || priceInvalid) return;
    const patch = answersToPatch(answers);

    if (provenance?.kind !== 'live' || Object.keys(patch).length === 0) {
      // A recorded run has no server-side listing; apply the answers the
      // way the server would, so the result reads the same.
      dispatch({ t: 'answered', listing: applyLocally(listing, patch) });
      return;
    }

    dispatch({ t: 'busy', busy: true });
    try {
      const saved = await api.patch(listing.id, patch);
      dispatch({ t: 'answered', listing: withAbsoluteImages(saved) });
    } catch {
      dispatch({ t: 'error', message: copy.demo.missingSaveFailed });
    }
  }

  const set = (field: AskField, value: string) =>
    setAnswers((a) => ({ ...a, [field]: value }));

  return (
    <Scaffold
      step={3}
      stepCount={3}
      actions={
        <BigActionButton
          label={copy.demo.missingConfirm}
          icon="arrow_forward"
          busy={busy}
          disabled={priceInvalid}
          onClick={() => void submit()}
        />
      }
    >
      <ScreenHeader
        title={copy.demo.missingTitle(fields.length)}
        subtitle={fields.length ? copy.demo.missingBody(fields.length) : undefined}
      />

      <div className={css.context}>
        <img
          className={css.contextThumb}
          src={listing.image_urls[0] ?? photo?.url}
          alt=""
        />
        <p className={css.contextTitle}>{listing.title}</p>
      </div>

      {listing.follow_up_question ? (
        <Panel icon="photo_camera">
          <span className={css.panelLabel}>{copy.demo.photoNote}</span>
          {listing.follow_up_question}
        </Panel>
      ) : null}

      {fields.length ? (
        <form
          className={css.questions}
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          {fields.map((field) => {
            const q = QUESTION[field];
            const isPrice = field === 'price';
            const suggested = listing.suggested_price_in_paise;
            const placeholder = isPrice
              ? suggested
                ? copy.demo.missingPriceHint(rupees(suggested))
                : copy.correctTypeHint
              : (q.hint ?? copy.correctTypeHint);
            const invalid = isPrice && priceInvalid && touchedPrice;
            return (
              <label key={field} className={css.question}>
                <span className={css.questionLabel}>{q.label}</span>
                {why.get(field) ? (
                  <span className={css.questionWhy}>{why.get(field)}</span>
                ) : isPrice ? (
                  <span className={css.questionWhy}>{copy.priceBody}</span>
                ) : null}
                <span className={`${css.inputWrap} ${invalid ? css.inputInvalid : ''}`}>
                  {isPrice ? <span className={css.prefix}>₹</span> : null}
                  <input
                    className={css.input}
                    name={field}
                    value={answers[field] ?? ''}
                    onChange={(e) => set(field, e.target.value)}
                    onBlur={() => isPrice && setTouchedPrice(true)}
                    placeholder={placeholder}
                    inputMode={isPrice ? 'decimal' : 'text'}
                    autoComplete="off"
                    maxLength={isPrice ? 12 : 120}
                  />
                </span>
                {invalid ? (
                  <span className={css.fieldError}>{copy.demo.missingPriceInvalid}</span>
                ) : null}
              </label>
            );
          })}
          {/* Lets Enter submit from any field. */}
          <button type="submit" hidden />
        </form>
      ) : null}

      {fields.length ? <p className={css.skipNote}>{copy.demo.missingSkip}</p> : null}

      {error ? <Panel tone="danger">{error}</Panel> : null}
    </Scaffold>
  );
}
