import type { ReactNode } from 'react';

import { Icon } from './Icon';
import { StepProgress } from './StepProgress';
import css from './Scaffold.module.css';

interface Props {
  /** 'close' shows an X (capture), 'back' shows an arrow (review). */
  leading?: 'close' | 'back' | 'none';
  onLeading?: () => void;
  /** 1-based; omitted hides the step bar. */
  step?: number;
  stepCount?: number;
  children: ReactNode;
  /** Bottom action stack — usually BigActionButtons. */
  actions?: ReactNode;
  /** Badge in the status bar, e.g. "Demo data". */
  pill?: string | null;
}

/**
 * The chrome every screen sits in. Mirrors CaptureScaffold / ReviewScaffold
 * plus a fake status bar and home indicator, which stand in for SafeArea and
 * make the viewport read as a phone rather than a rounded div.
 */
export function Scaffold({
  leading = 'none',
  onLeading,
  step,
  stepCount,
  children,
  actions,
  pill,
}: Props) {
  return (
    <div className={css.root}>
      <div className={css.statusBar}>
        <span>9:41</span>
        <span className={css.statusRight}>
          {pill ? <span className={css.pill}>{pill}</span> : null}
          <span className={css.statusGlyphs} aria-hidden="true">
            <SignalGlyph />
            <BatteryGlyph />
          </span>
        </span>
      </div>

      <div className={`${css.appBar} ${leading === 'none' ? css.appBarEmpty : ''}`}>
        {leading === 'none' ? (
          <span className={css.appBarSpacer} />
        ) : (
          <button
            type="button"
            className={css.appBarButton}
            onClick={onLeading}
            aria-label={leading === 'close' ? 'Close' : 'Go back'}
          >
            <Icon name={leading === 'close' ? 'close' : 'arrow_back'} size={30} />
          </button>
        )}
        <span className={css.appBarTitleSlot} />
        <span className={css.appBarSpacer} />
      </div>

      {step && stepCount ? <StepProgress step={step} total={stepCount} /> : null}

      <div className={css.body}>{children}</div>

      {actions ? <div className={css.actions}>{actions}</div> : null}

      <div className={css.homeIndicator}>
        <span className={css.homeBar} />
      </div>
    </div>
  );
}

function SignalGlyph() {
  return (
    <svg width="17" height="11" viewBox="0 0 17 11" fill="currentColor">
      <rect x="0" y="7" width="3" height="4" rx="1" />
      <rect x="4.7" y="5" width="3" height="6" rx="1" />
      <rect x="9.4" y="2.6" width="3" height="8.4" rx="1" />
      <rect x="14" y="0" width="3" height="11" rx="1" />
    </svg>
  );
}

function BatteryGlyph() {
  return (
    <svg width="25" height="12" viewBox="0 0 25 12" fill="none">
      <rect
        x="0.5"
        y="0.5"
        width="21"
        height="11"
        rx="3"
        stroke="currentColor"
        opacity="0.5"
      />
      <rect x="2" y="2" width="14" height="8" rx="1.6" fill="currentColor" />
      <path
        d="M23 4.2v3.6c.9-.3 1.5-1 1.5-1.8S23.9 4.5 23 4.2Z"
        fill="currentColor"
        opacity="0.5"
      />
    </svg>
  );
}
