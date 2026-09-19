import { copy } from '../../copy/en';
import { dispatch, useDemo } from '../../machine/store';
import {
  NUDGE_LARGE_PAISE,
  NUDGE_SMALL_PAISE,
  PRICE_STEP_PAISE,
  priceBand,
  priceFloor,
  rupees,
  sliderCeiling,
} from '../../util/money';
import { BigActionButton } from '../widgets/BigActionButton';
import { Panel } from './Panel';
import { ReviewScaffold } from './ReviewScaffold';
import css from './review.module.css';

/**
 * "What is the price?"
 *
 * The floor is what the work cost to make. Going below it is allowed — the
 * app deliberately lets the seller decide — but it says so plainly, which is
 * the whole reason this screen exists rather than a bare number field.
 */
export function PriceStage() {
  const { listing, priceInPaise } = useDemo();
  if (!listing) return null;

  const facts = listing.fact_sheet;
  const floor = priceFloor(
    listing.price_floor_in_paise,
    facts.material_cost_in_paise,
    facts.hours_to_make,
  );
  const value = priceInPaise ?? listing.suggested_price_in_paise ?? floor ?? 100_000;
  const ceiling = sliderCeiling(floor);
  const band = floor != null ? priceBand(floor) : null;
  const belowFloor = floor != null && value < floor;

  const set = (paise: number) =>
    dispatch({ t: 'price', paise: Math.max(PRICE_STEP_PAISE, Math.min(ceiling, paise)) });

  return (
    <ReviewScaffold
      title={copy.priceTitle}
      subtitle={copy.priceBody}
      actions={
        <BigActionButton
          label={copy.priceConfirm}
          icon="check"
          onClick={() => dispatch({ t: 'reviewNext' })}
        />
      }
    >
      <p className={css.priceValue}>{rupees(value)}</p>

      <input
        className={css.slider}
        type="range"
        min={PRICE_STEP_PAISE}
        max={ceiling}
        step={PRICE_STEP_PAISE}
        value={value}
        onChange={(e) => set(Number(e.target.value))}
        aria-label={copy.priceTitle}
      />

      <div className={css.nudgeRow}>
        <button type="button" className={css.nudge} onClick={() => set(value - NUDGE_LARGE_PAISE)}>
          −{rupees(NUDGE_LARGE_PAISE)}
        </button>
        <button type="button" className={css.nudge} onClick={() => set(value - NUDGE_SMALL_PAISE)}>
          −{rupees(NUDGE_SMALL_PAISE)}
        </button>
        <button type="button" className={css.nudge} onClick={() => set(value + NUDGE_SMALL_PAISE)}>
          +{rupees(NUDGE_SMALL_PAISE)}
        </button>
        <button type="button" className={css.nudge} onClick={() => set(value + NUDGE_LARGE_PAISE)}>
          +{rupees(NUDGE_LARGE_PAISE)}
        </button>
      </div>

      {band ? (
        <p className={css.bandRow}>{copy.priceBand(rupees(band.low), rupees(band.high))}</p>
      ) : null}

      {floor != null ? <Panel>{copy.priceFloor(rupees(floor))}</Panel> : null}

      {belowFloor ? <Panel tone="danger">{copy.priceBelowFloor}</Panel> : null}
    </ReviewScaffold>
  );
}
