import { copy } from '../../copy/en';
import type { QueueState } from '../../machine/types';
import { Icon, type IconName } from '../widgets/Icon';
import css from './processing.module.css';

/**
 * The app's queue status line, ported from
 * app/lib/features/queue/widgets/queue_state_line.dart — same four states,
 * same copy, same icons, same colours. This is the progression a seller sees
 * on the phone, so the demo shows it verbatim.
 */
export function QueueLine({ queue }: { queue: QueueState }) {
  const spec = describe(queue);
  if (!spec) return null;

  return (
    <div>
      <p className={`${css.queueLine} ${css[spec.tone]}`}>
        <Icon name={spec.icon} size={22} />
        {spec.label}
      </p>
      {queue.kind === 'uploading' ? (
        <div className={css.uploadTrack}>
          <div className={css.uploadFill} style={{ width: `${queue.percent}%` }} />
        </div>
      ) : null}
    </div>
  );
}

function describe(
  queue: QueueState,
): { label: string; icon: IconName; tone: 'waiting' | 'uploading' | 'processing' | 'failed' } | null {
  switch (queue.kind) {
    case 'waiting':
      return { label: copy.queueStateWaiting, icon: 'schedule', tone: 'waiting' };
    case 'uploading':
      return {
        label: copy.queueStateUploading(queue.percent),
        icon: 'cloud_upload',
        tone: 'uploading',
      };
    case 'processing':
      return {
        label: copy.queueStateProcessing,
        icon: 'hourglass_bottom',
        tone: 'processing',
      };
    case 'failed':
      return { label: copy.queueStateFailed, icon: 'error_outline', tone: 'failed' };
    case 'idle':
      return null;
  }
}
