import { useCallback, useRef } from 'react';

import { Icon } from './Icon';
import css from './HoldToSpeakButton.module.css';

interface Props {
  recording: boolean;
  label: string;
  onStart: () => void;
  onStop: () => void;
  disabled?: boolean;
}

/**
 * Press and hold to record; release to stop.
 *
 * Pointer events rather than mouse/touch pairs, so pen and touch behave the
 * same. `setPointerCapture` means a finger that slides off the button still
 * stops the recording on release instead of leaving it running forever, and
 * that a thumb drifting a few pixels while it talks does not stop it early.
 *
 * `onStart` is called synchronously inside the pointerdown or keydown, and
 * must stay that way: the recorder builds its AudioContext there, and iOS
 * only lets one start inside a gesture.
 */
export function HoldToSpeakButton({
  recording,
  label,
  onStart,
  onStop,
  disabled = false,
}: Props) {
  // Which press is holding the button: a pointer id, 'key', or null. Tied to
  // the press rather than a plain flag so that a second finger landing and
  // lifting mid-sentence cannot end the first finger's recording.
  const held = useRef<number | 'key' | null>(null);

  const press = useCallback(
    (by: number | 'key') => {
      if (disabled || held.current !== null) return false;
      held.current = by;
      navigator.vibrate?.(12);
      onStart();
      return true;
    },
    [disabled, onStart],
  );

  const release = useCallback(
    (by: number | 'key') => {
      if (held.current !== by) return;
      held.current = null;
      navigator.vibrate?.(12);
      onStop();
    },
    [onStop],
  );

  const down = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      // A right-click or a middle-click is not a press.
      if (e.button !== 0) return;
      if (!press(e.pointerId)) return;
      try {
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch {
        // The pointer can already be gone (the permission prompt took it);
        // pointercancel follows and ends the press.
      }
    },
    [press],
  );

  // pointercancel is what a phone sends when something takes the touch away:
  // the permission prompt on the first press, an incoming call, a system
  // gesture. No pointerup will follow, so the press has to end here or the
  // recording runs on with no finger on the button. lostpointercapture
  // covers the rest, such as the button leaving the page mid-press; after a
  // normal pointerup it arrives second and finds nothing held.
  const up = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => release(e.pointerId),
    [release],
  );

  const isKey = (e: React.KeyboardEvent) => e.key === ' ' || e.key === 'Enter';

  return (
    <div className={css.wrap}>
      <span
        className={`${css.ring} ${recording ? css.ringOn : ''}`}
        aria-hidden="true"
      />
      <span
        className={`${css.ring} ${css.ringDelayed} ${recording ? css.ringOn : ''}`}
        aria-hidden="true"
      />
      <button
        type="button"
        className={`${css.button} ${recording ? css.recording : ''}`}
        disabled={disabled}
        onPointerDown={down}
        onPointerUp={up}
        onPointerCancel={up}
        onLostPointerCapture={up}
        // Android answers a long press with a context menu, which cancels
        // the pointer and would cut the recording off mid-sentence.
        onContextMenu={(e) => e.preventDefault()}
        // Keyboard equivalent: hold space or enter, as a finger holds the
        // button. A held key repeats keydown many times a second, and the
        // recording starts asynchronously, so the repeats are dropped here
        // rather than left to look like new presses.
        onKeyDown={(e) => {
          if (!isKey(e)) return;
          e.preventDefault();
          if (!e.repeat) press('key');
        }}
        onKeyUp={(e) => {
          if (!isKey(e)) return;
          e.preventDefault();
          release('key');
        }}
        // Focus leaving mid-hold means the keyup will land somewhere else.
        onBlur={() => release('key')}
      >
        <Icon name={recording ? 'stop' : 'mic'} size={32} />
        {label}
      </button>
    </div>
  );
}
