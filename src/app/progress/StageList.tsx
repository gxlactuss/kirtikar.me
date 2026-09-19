import { STAGES } from '../../machine/ticker';
import type { Progress } from '../../machine/types';
import { Icon } from '../widgets/Icon';
import css from './processing.module.css';

/** Threshold past which the bar has effectively stopped moving on its own. */
const SHIMMER_AT = 0.9;

/**
 * The five backend pipeline stages.
 *
 * These are the real stage names from services/pipeline/runner.py. The
 * server reports only start and finish, so the pacing between them is
 * estimated — the explainer panel beside the phone says so outright, because
 * a judge who asks deserves a straight answer.
 */
export function StageList({ progress }: { progress: Progress }) {
  return (
    <div className={css.stages}>
      {STAGES.map((stage, i) => {
        const done = progress.done[i] ?? false;
        const active = !done && i === progress.stageIndex;
        const pct = active ? progress.stageProgress : done ? 1 : 0;
        const shimmer = active && progress.stageProgress >= SHIMMER_AT;

        return (
          <div className={css.stage} key={stage.id}>
            <span className={css.stageIcon}>
              {done ? (
                <Icon name="check_circle" size={26} color="var(--success)" />
              ) : (
                <span
                  className={css.dot}
                  style={active ? { borderColor: 'var(--terracotta)' } : undefined}
                />
              )}
            </span>

            <span className={css.stageBody}>
              <span
                className={`${css.stageLabel} ${
                  active ? css.stageLabelActive : done ? css.stageLabelDone : ''
                }`}
              >
                {stage.label}
              </span>
              {active ? (
                <span className={`${css.stageTrack} ${shimmer ? css.stageShimmer : ''}`}>
                  <span className={css.stageFill} style={{ width: `${pct * 100}%` }} />
                </span>
              ) : null}
            </span>
          </div>
        );
      })}
    </div>
  );
}
