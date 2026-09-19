import css from './StepProgress.module.css';

interface Props {
  step: number;
  total: number;
}

/** "Step 3 of 7" plus a 6px bar that animates over 450ms. */
export function StepProgress({ step, total }: Props) {
  const pct = Math.max(0, Math.min(1, step / total)) * 100;
  return (
    <div className={css.root}>
      <div
        className={css.track}
        role="progressbar"
        aria-valuenow={step}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label={`Step ${step} of ${total}`}
      >
        <div className={css.fill} style={{ width: `${pct}%` }} />
      </div>
      <span className={css.label}>
        Step {step} of {total}
      </span>
    </div>
  );
}
