/** The five switchable viewport sizes.
 *
 * These are CSS pixel dimensions, not scale factors: picking one genuinely
 * resizes the viewport so layout recomputes and text rewraps. The optical
 * `zoom` control is separate and deliberately orthogonal — see DeviceFrame.
 */
export interface DevicePreset {
  readonly id: string;
  readonly label: string;
  readonly inches: string;
  readonly width: number;
  readonly height: number;
  /** Shown in the explainer so a judge knows why this size is in the list. */
  readonly standsFor: string;
  /** Exactly one preset carries this: the device the product actually targets. */
  readonly isTarget?: boolean;
}

export const DEVICES: readonly DevicePreset[] = [
  {
    id: 'large',
    label: 'Large phone',
    inches: '6.9"',
    width: 440,
    height: 956,
    standsFor: 'iPhone 17 Pro Max, Pixel 9 Pro XL',
  },
  {
    id: 'standard',
    label: 'Standard phone',
    inches: '6.3"',
    width: 402,
    height: 874,
    standsFor: 'iPhone 17, Pixel 9',
  },
  {
    id: 'common',
    label: 'Common',
    inches: '6.1"',
    width: 390,
    height: 844,
    standsFor: 'iPhone 15, Galaxy A-series',
  },
  {
    id: 'budget',
    label: 'Budget Android',
    inches: '6.5"',
    width: 360,
    height: 800,
    standsFor: 'Redmi A3 and most sub-₹12,000 handsets',
    isTarget: true,
  },
  {
    id: 'small',
    label: 'Very small',
    inches: '4.7"',
    width: 320,
    height: 568,
    standsFor: 'iPhone SE — the tap-target stress test',
  },
] as const;

/** Index into DEVICES. Defaults to the device the product actually targets. */
export const DEFAULT_DEVICE = DEVICES.findIndex((d) => d.isTarget);

export const TALLEST = Math.max(...DEVICES.map((d) => d.height));

/** Bezel thickness around the viewport, in unscaled px. */
export const BEZEL = 12;

/**
 * Pick an optical zoom that fits the tallest preset into the available height.
 *
 * Rounded to 0.05 steps because fractional scales blur glyph rasterisation,
 * and capped at 1.30 so a 320x568 frame doesn't balloon into a tablet on a
 * 4K display.
 */
export function fitZoom(availableHeight: number): number {
  const raw = (availableHeight - 72) / (TALLEST + BEZEL * 2);
  return clampZoom(Math.round(raw * 20) / 20);
}

/**
 * On a tablet the size picker is hidden, so the frame never changes preset
 * and there is nothing to keep steady: fit the one it shows, by width as well
 * as height, rather than shrinking it to leave room for the tallest.
 */
export function fitZoomTo(device: DevicePreset, width: number, height: number): number {
  const raw = Math.min(
    (height - 120) / (device.height + BEZEL * 2),
    (width - 32) / (device.width + BEZEL * 2),
  );
  // Floored, not rounded: rounding up would push the frame off the screen.
  return clampZoom(Math.floor(raw * 20) / 20);
}

function clampZoom(zoom: number): number {
  return Math.min(1.3, Math.max(0.55, zoom));
}

/**
 * Below this the screen is itself a phone. A phone drawn inside a phone
 * shrinks every tap target to half size, so the app takes the whole screen
 * instead and the frame goes away. Mirrored in stage.module.css and
 * intro.module.css.
 */
export const NATIVE_QUERY = '(max-width: 600px)';

/** A phone on its side: too short for a portrait app at any usable scale. */
export const SIDEWAYS_QUERY = '(max-height: 500px) and (orientation: landscape) and (pointer: coarse)';

/** Matches DeviceFrame's stacked layout in stage.module.css. */
export const STACKED_QUERY = '(max-width: 1100px)';
