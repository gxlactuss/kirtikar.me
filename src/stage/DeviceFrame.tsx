import type { ReactNode } from 'react';

import { BEZEL, type DevicePreset } from './devices';
import css from './stage.module.css';

interface Props {
  device: DevicePreset;
  zoom: number;
  /** The screen is itself a phone: no frame, the app fills it. */
  native?: boolean;
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
 *
 * `native` drops the frame on a real phone. It only restyles: the element
 * tree stays the same, so crossing the breakpoint never remounts the app
 * and loses a run in progress.
 */
export function DeviceFrame({ device, zoom, native = false, children }: Props) {
  return (
    <div
      className={css.deviceSlot}
      data-native={native ? '1' : '0'}
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
        <div className={css.bezel} data-bezel>
          <div
            className={css.viewport}
            data-device={native ? 'native' : device.id}
            data-width={device.width}
            data-native={native ? '1' : '0'}
          >
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
