/**
 * Money is integer paise everywhere, matching the backend's *_in_paise
 * columns. Only the display layer knows about rupees.
 *
 * Careful: GET /readback and GET /preview return `price` as a FLOAT in
 * rupees while everything else is integer paise. This module never touches
 * those two endpoints, and neither does the demo.
 */

export const PAISE_PER_RUPEE = 100;

/** Ported from ReviewConstants (app/lib/core/constants/review_constants.dart). */
export const HOURLY_RATE_IN_PAISE = 6000;
export const BAND_LOW = 1.2;
export const BAND_HIGH = 1.8;
export const SLIDER_CEILING_MULTIPLIER = 4;

export const PRICE_STEP_PAISE = 1000; // ₹10
export const NUDGE_SMALL_PAISE = 1000; // ₹10
export const NUDGE_LARGE_PAISE = 5000; // ₹50

const FORMAT = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

/** "₹1,200" */
export function rupees(paise: number | null | undefined): string {
  if (paise == null) return '—';
  return FORMAT.format(Math.round(paise / PAISE_PER_RUPEE));
}

export const toPaise = (rupeeValue: number): number =>
  Math.round(rupeeValue * PAISE_PER_RUPEE);

export const toRupees = (paise: number): number => paise / PAISE_PER_RUPEE;

/**
 * What the work cost to make.
 *
 * The server usually supplies price_floor_in_paise. When it does not, fall
 * back to the app's own sum: materials plus time at the hourly rate.
 */
export function priceFloor(
  serverFloor: number | null,
  materialCostInPaise: number | null,
  hoursToMake: number | null,
): number | null {
  if (serverFloor != null) return serverFloor;
  if (materialCostInPaise == null && hoursToMake == null) return null;
  return (
    (materialCostInPaise ?? 0) + Math.round((hoursToMake ?? 0) * HOURLY_RATE_IN_PAISE)
  );
}

/** "Others sell this kind of thing for X to Y" */
export function priceBand(floor: number): { low: number; high: number } {
  return {
    low: Math.round(floor * BAND_LOW),
    high: Math.round(floor * BAND_HIGH),
  };
}

/** Upper bound of the price slider, clamped the way the app clamps it. */
export function sliderCeiling(floor: number | null): number {
  const raw = (floor ?? 50_000) * SLIDER_CEILING_MULTIPLIER;
  return Math.max(200_000, Math.min(10_000_000, raw));
}
