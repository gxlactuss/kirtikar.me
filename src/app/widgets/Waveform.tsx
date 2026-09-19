import css from './Waveform.module.css';

export const BAR_COUNT = 21;

interface Props {
  /** 0..1 current input level. */
  level: number;
  active: boolean;
}

/**
 * The 21-bar level meter.
 *
 * Bar height is `(8 + level * 66 * shape).clamp(8, 76)` where
 * `shape = 1 - dist^2 * 0.75` — a bell curve so the middle bars swing
 * furthest and the ends stay short. Straight from waveform.dart.
 */
export function Waveform({ level, active }: Props) {
  const mid = (BAR_COUNT - 1) / 2;

  return (
    <div className={css.root} aria-hidden="true">
      {Array.from({ length: BAR_COUNT }, (_, i) => {
        const dist = Math.abs(i - mid) / mid;
        const shape = 1 - dist * dist * 0.75;
        const height = Math.max(8, Math.min(76, 8 + level * 66 * shape));
        return (
          <span
            key={i}
            className={`${css.bar} ${active ? css.active : ''}`}
            style={{ height: `${height}px` }}
          />
        );
      })}
    </div>
  );
}

/** Static version for playback, driven by recorded peaks rather than live level. */
export function WaveformPeaks({ peaks }: { peaks: number[] }) {
  const mid = (BAR_COUNT - 1) / 2;
  // Bucket the recorded peaks down to the 21 bars.
  const buckets = Array.from({ length: BAR_COUNT }, (_, i) => {
    const from = Math.floor((i / BAR_COUNT) * peaks.length);
    const to = Math.max(from + 1, Math.floor(((i + 1) / BAR_COUNT) * peaks.length));
    const slice = peaks.slice(from, to);
    return slice.length ? Math.max(...slice) : 0;
  });

  return (
    <div className={css.root} aria-hidden="true">
      {buckets.map((value, i) => {
        const dist = Math.abs(i - mid) / mid;
        const shape = 1 - dist * dist * 0.75;
        const height = Math.max(8, Math.min(76, 8 + value * 66 * shape));
        return (
          <span
            key={i}
            className={`${css.bar} ${css.active}`}
            style={{ height: `${height}px` }}
          />
        );
      })}
    </div>
  );
}
