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
 * stops the recording on release instead of leaving it running forever.
 */
export function HoldToSpeakButton({
  recording,
  label,
  onStart,
  onStop,
  disabled = false,
}: Props) {
  const held = useRef(false);

  const down = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      if (disabled || held.current) return;
      held.current = true;
      e.currentTarget.setPointerCapture(e.pointerId);
      navigator.vibrate?.(12);
      onStart();
    },
    [disabled, onStart],
  );

  const up = useCallback(() => {
    if (!held.current) return;
    held.current = false;
    navigator.vibrate?.(12);
    onStop();
  }, [onStop]);

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
        // Android answers a long press with a context menu, which cancels
        // the pointer and would cut the recording off mid-sentence.
        onContextMenu={(e) => e.preventDefault()}
        // Keyboard equivalent: space/enter toggles rather than holds.
        onKeyDown={(e) => {
          if ((e.key === ' ' || e.key === 'Enter') && !recording) {
            e.preventDefault();
            onStart();
          }
        }}
        onKeyUp={(e) => {
          if ((e.key === ' ' || e.key === 'Enter') && recording) {
            e.preventDefault();
            onStop();
          }
        }}
      >
        <Icon name={recording ? 'stop' : 'mic'} size={32} />
        {label}
      </button>
    </div>
  );
}
