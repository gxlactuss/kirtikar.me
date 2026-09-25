import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import {
  DEVICES,
  DEFAULT_DEVICE,
  NATIVE_QUERY,
  SIDEWAYS_QUERY,
  STACKED_QUERY,
  fitZoom,
  fitZoomTo,
} from './devices';
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
  const [available, setAvailable] = useState(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
  }));
  const native = useMedia(NATIVE_QUERY);
  const sideways = useMedia(SIDEWAYS_QUERY);
  const stacked = useMedia(STACKED_QUERY);

  // null means "follow the window"; a number means the user took over.
  const [manualZoom, setManualZoom] = useState<number | null>(null);

  const device = DEVICES[index] ?? DEVICES[DEFAULT_DEVICE]!;

  const autoZoom = useMemo(
    () =>
      stacked
        ? fitZoomTo(device, available.width, available.height)
        : fitZoom(available.height),
    [stacked, device, available],
  );
  const zoom = manualZoom ?? autoZoom;

  const frameRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onResize = () =>
      setAvailable({ width: window.innerWidth, height: window.innerHeight });
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

  return (
    <div className={`${css.stage} stageScope`} data-native={native ? '1' : '0'}>
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
        <DeviceFrame device={device} zoom={zoom} native={native}>
          {children}
        </DeviceFrame>
      </div>

      {/* Laid over the app, never swapped for it, so turning the phone back
          upright finds the run exactly where it was. */}
      {sideways ? (
        <div className={css.sideways} role="alert">
          <span className={css.sidewaysIcon} aria-hidden="true">
            ⟳
          </span>
          Turn your phone upright to use the demo.
        </div>
      ) : null}
    </div>
  );
}

function useMedia(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    onChange();
    list.addEventListener('change', onChange);
    return () => list.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}
