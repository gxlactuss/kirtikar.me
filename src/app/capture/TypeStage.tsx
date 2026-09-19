import { useState } from 'react';

import { copy } from '../../copy/en';
import { CRAFT_BY_SLUG } from '../crafts';
import { dispatch, useDemo } from '../../machine/store';
import { BigActionButton } from '../widgets/BigActionButton';
import { Scaffold } from '../widgets/Scaffold';
import { ScreenHeader } from '../widgets/ScreenHeader';
import css from './voice.module.css';

const MIN_CHARS = 12;

/**
 * The typed alternative to the voice note.
 *
 * Sent as `description` on POST /listings, which makes the backend skip its
 * speech stage entirely (stages/speech.py:35-45) and go straight to Gemini.
 * Useful for a judge on a laptop with no microphone, or in a noisy hall.
 */
export function TypeStage() {
  const { photos, typed } = useDemo();
  const [text, setText] = useState(typed ?? '');

  const hint = photos[0] ? CRAFT_BY_SLUG.get(photos[0].slug)?.hint : undefined;
  const ready = text.trim().length >= MIN_CHARS;

  return (
    <Scaffold
      leading="back"
      onLeading={() => dispatch({ t: 'goCapture', stage: 'voiceRecord' })}
      step={2}
      stepCount={2}
      actions={
        <BigActionButton
          label={copy.demo.typeConfirm}
          icon="check"
          disabled={!ready}
          onClick={() => {
            dispatch({ t: 'typed', text: text.trim() });
            dispatch({ t: 'submit' });
          }}
        />
      }
    >
      <ScreenHeader title={copy.demo.typeTitle} subtitle={copy.voiceBody} />

      <textarea
        className={css.textarea}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={hint ?? copy.demo.typeHint}
        maxLength={600}
        autoFocus
      />
      <p className={css.counter}>
        {ready ? `${text.trim().length} characters` : `At least ${MIN_CHARS} characters`}
      </p>
    </Scaffold>
  );
}
