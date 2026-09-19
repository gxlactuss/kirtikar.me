import { useEffect } from 'react';

import { copy } from '../../copy/en';
import { pendingSuggestion } from '../../machine/reducer';
import { dispatch, store, useDemo } from '../../machine/store';
import { BigActionButton } from '../widgets/BigActionButton';
import { ReviewScaffold } from './ReviewScaffold';
import css from './review.module.css';

/**
 * "Shall we add this?" — the pipeline noticed a gap and proposes a filler.
 *
 * Suggestions come from `missing_fields` on the Gemini extraction, mapped to
 * prompts server-side. Each decision is POSTed to the approval endpoint;
 * the wizard advances locally without waiting for it.
 */
export function SuggestionsStage() {
  const state = useDemo();
  const suggestion = pendingSuggestion(state);

  // Nothing pending: the reducer's skip should have prevented this, but the
  // decision on the last suggestion lands here for one render. Moving on in
  // an effect, because a dispatch during render updates every other store
  // subscriber mid-render.
  useEffect(() => {
    if (!suggestion) dispatch({ t: 'reviewGo', stage: 'price' });
  }, [suggestion]);

  if (!suggestion) return null;

  const total = state.listing?.suggestions.length ?? 0;
  const answered = Object.keys(state.suggestionDecisions).length;

  // Event handlers are outside render, so dispatching twice here is fine.
  const decide = (approved: boolean) => {
    dispatch({ t: 'suggestion', id: suggestion.id, approved });
    if (!pendingSuggestion(store.peek())) dispatch({ t: 'reviewGo', stage: 'price' });
  };

  return (
    <ReviewScaffold
      title={copy.suggestTitle}
      actions={
        <>
          <BigActionButton label={copy.suggestYes} icon="check" onClick={() => decide(true)} />
          <BigActionButton
            label={copy.suggestNo}
            icon="close"
            tone="secondary"
            onClick={() => decide(false)}
          />
        </>
      }
    >
      <p className={css.suggestPrompt}>{suggestion.spoken_prompt}</p>
      {suggestion.text_if_accepted ? (
        <div className={css.titleBlock}>
          <p className={css.listingDesc}>{suggestion.text_if_accepted}</p>
        </div>
      ) : null}
      <p className={css.suggestCounter}>{copy.suggestProgress(answered + 1, total)}</p>
    </ReviewScaffold>
  );
}
