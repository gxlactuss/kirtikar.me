import type { ReactNode } from 'react';

import { BEZEL, type DevicePreset } from './devices';
import css from './stage.module.css';

interface Props {
  device: DevicePreset;
  zoom: number;
  children: ReactNode;
}

/**
 * The phone shell.
 *
 * Two orthogonal controls, deliberately never conflated:
 *
 *   - `device` sets the viewport's real CSS pixel size, so layout inside
 *     genuinely recomputes and text rewraps. This is what makes the demo
 *     honest about small screens.
 *   - `zoom` is a transform on an outer wrapper. It changes how big the
 *     frame looks on the desk, and nothing else. The inner viewport still
 *     reports its true width to @container queries and to devtools.
 *
 * Scaling in place of resizing would be the easy version and would lie.
 */
export function DeviceFrame({ device, zoom, children }: Props) {
  return (
    <div
      className={css.deviceSlot}
      style={
        {
          '--vw': `${device.width}px`,
          '--vh': `${device.height}px`,
          '--bezel': `${BEZEL}px`,
          '--zoom': zoom,
        } as React.CSSProperties
      }
    >
      <div className={css.deviceScale}>
        <div className={css.bezel}>
          <div
            className={css.viewport}
            data-device={device.id}
            data-width={device.width}
          >
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
