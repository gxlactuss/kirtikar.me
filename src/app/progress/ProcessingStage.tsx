import { copy } from '../../copy/en';
import { store, useDemo } from '../../machine/store';
import { BigActionButton } from '../widgets/BigActionButton';
import { Icon } from '../widgets/Icon';
import { Scaffold } from '../widgets/Scaffold';
import { ScreenHeader } from '../widgets/ScreenHeader';
import { QueueLine } from './QueueLine';
import { StageList } from './StageList';
import css from './processing.module.css';

/**
 * What the seller watches while the pipeline runs.
 *
 * Upload percentage is real bytes off the wire. The five stage rows are
 * paced from measured runs and gated on the server's answer — see
 * machine/ticker.ts for the rules that keeps honest.
 */
export function ProcessingStage() {
  const { progress, photos, provenance, error } = useDemo();
  const uploading = progress.queue.kind === 'uploading';

  // Both the live call and the recorded replay failed. The ticker has
  // stopped, so without this the seller is left watching a frozen progress
  // bar with no way out.
  if (error) {
    return (
      <Scaffold>
        <ScreenHeader title={copy.demo.processingFailedTitle} subtitle={error} />
        <BigActionButton
          label={copy.demo.processingFailedAction}
          icon="refresh"
          onClick={() => store.dispatch({ t: 'reset' })}
        />
      </Scaffold>
    );
  }

  return (
    <Scaffold pill={provenance?.kind === 'fixture' ? copy.demo.demoDataPill : null}>
      <ScreenHeader
        title={copy.queueStateProcessing}
        subtitle={copy.demo.processingBody}
      />

      {photos.length ? (
        <div className={css.thumbs}>
          {photos.map((p) => (
            <img className={css.thumb} key={p.url} src={p.url} alt="" />
          ))}
        </div>
      ) : null}

      <QueueLine queue={progress.queue} />

      {!uploading ? (
        <>
          <StageList progress={progress} />

          <div className={css.overall}>
            <div className={css.overallTrack}>
              <div
                className={css.overallFill}
                style={{ width: `${progress.overall * 100}%` }}
              />
            </div>
            <p className={css.overallLabel}>
              <span>{progress.finished ? copy.actionDone : 'Working'}</span>
              <span>{Math.floor(progress.overall * 100)}%</span>
            </p>
          </div>
        </>
      ) : null}

      {progress.slow ? (
        <div className={css.slow}>
          <Icon name="lightbulb" size={22} className={css.slowIcon} />
          <span>{copy.demo.processingSlow}</span>
        </div>
      ) : null}
    </Scaffold>
  );
}
