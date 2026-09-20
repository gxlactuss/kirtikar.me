import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { DEVICES, DEFAULT_DEVICE, fitZoom } from './devices';
import { DeviceFrame } from './DeviceFrame';
import { DeviceSizePicker } from './DeviceSizePicker';
import css from './stage.module.css';

interface Props {
  children: ReactNode;
  /** Rendered in the left column, under the size picker. */
  aside?: ReactNode;
}

/**
 * The black desk the phone sits on. Owns device size and optical zoom;
 * everything else lives inside the frame.
 */
export function Stage({ children, aside }: Props) {
  const [index, setIndex] = useState(DEFAULT_DEVICE);
  const [available, setAvailable] = useState(() => window.innerHeight);

  // null means "follow the window"; a number means the user took over.
  const [manualZoom, setManualZoom] = useState<number | null>(null);

  const autoZoom = useMemo(() => fitZoom(available), [available]);
  const zoom = manualZoom ?? autoZoom;

  const frameRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onResize = () => setAvailable(window.innerHeight);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const pick = useCallback((i: number) => setIndex(i), []);

  // 1-5 switch size, 0 restores automatic zoom. Ignored while the visitor is
  // typing, so the price and description fields keep their digits.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = document.activeElement;
      if (
        el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement ||
        (el instanceof HTMLElement && el.isContentEditable)
      ) {
        return;
      }
      if (e.key >= '1' && e.key <= String(DEVICES.length)) {
        setIndex(Number(e.key) - 1);
      } else if (e.key === '0') {
        setManualZoom(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const device = DEVICES[index] ?? DEVICES[DEFAULT_DEVICE]!;

  return (
    <div className={`${css.stage} stageScope`}>
      <div className={css.left}>
        <DeviceSizePicker
          index={index}
          onPick={pick}
          zoom={zoom}
          onZoom={setManualZoom}
          autoZoom={autoZoom}
        />
        {aside}
      </div>

      <div className={css.deviceCell} ref={frameRef}>
        <DeviceFrame device={device} zoom={zoom}>
          {children}
        </DeviceFrame>
      </div>
    </div>
  );
}
