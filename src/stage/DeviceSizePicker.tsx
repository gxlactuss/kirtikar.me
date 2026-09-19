import { DEVICES } from './devices';
import css from './stage.module.css';

interface Props {
  index: number;
  onPick: (index: number) => void;
  zoom: number;
  onZoom: (zoom: number) => void;
  autoZoom: number;
}

const ZOOM_MIN = 0.4;
const ZOOM_MAX = 1.6;
const ZOOM_STEP = 0.1;

export function DeviceSizePicker({ index, onPick, zoom, onZoom, autoZoom }: Props) {
  const clamp = (z: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(z * 100) / 100));

  return (
    <div className={css.picker}>
      <p className={css.pickerTitle}>Screen size</p>

      {DEVICES.map((device, i) => (
        <button
          key={device.id}
          type="button"
          className={css.sizeButton}
          aria-pressed={i === index}
          onClick={() => onPick(i)}
          title={device.standsFor}
        >
          <span className={css.key} aria-hidden="true">
            {i + 1}
          </span>
          <span className={css.sizeName}>
            <span className={css.sizeLabel}>
              {device.label} · {device.inches}
            </span>
            <span className={css.sizeMeta}>
              {device.width} × {device.height}
            </span>
          </span>
          {device.isTarget ? <span className={css.targetTag}>Target</span> : <span />}
        </button>
      ))}

      <div className={css.zoomRow}>
        <span className={css.zoomLabel}>
          Zoom
          {Math.abs(zoom - autoZoom) > 0.001 ? '' : ' (auto)'}
        </span>
        <button
          type="button"
          className={css.zoomButton}
          onClick={() => onZoom(clamp(zoom - ZOOM_STEP))}
          disabled={zoom <= ZOOM_MIN}
          aria-label="Zoom out"
        >
          −
        </button>
        <span className={css.zoomValue}>{Math.round(zoom * 100)}%</span>
        <button
          type="button"
          className={css.zoomButton}
          onClick={() => onZoom(clamp(zoom + ZOOM_STEP))}
          disabled={zoom >= ZOOM_MAX}
          aria-label="Zoom in"
        >
          +
        </button>
      </div>
    </div>
  );
}
