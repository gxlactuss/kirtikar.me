import { copy } from '../../copy/en';
import { dispatch, useDemo } from '../../machine/store';
import { BigActionButton } from '../widgets/BigActionButton';
import { Icon } from '../widgets/Icon';
import { ReviewScaffold } from './ReviewScaffold';
import css from './review.module.css';

/** "How many do you have?" — stock, plus the one-of-a-kind shortcut. */
export function StockStage() {
  const { quantity, isOneOfAKind } = useDemo();

  return (
    <ReviewScaffold
      title={copy.stockTitle}
      subtitle={copy.stockBody}
      actions={
        <BigActionButton
          label={copy.actionDone}
          icon="check"
          onClick={() => dispatch({ t: 'reviewNext' })}
        />
      }
    >
      <div className={css.stepper}>
        <button
          type="button"
          className={css.stepperButton}
          onClick={() => dispatch({ t: 'quantity', n: quantity - 1 })}
          disabled={isOneOfAKind || quantity <= 0}
          aria-label={copy.stockLess}
        >
          <Icon name="remove" size={34} />
        </button>

        <span className={css.stepperValue} aria-live="polite">
          {quantity}
        </span>

        <button
          type="button"
          className={css.stepperButton}
          onClick={() => dispatch({ t: 'quantity', n: quantity + 1 })}
          disabled={isOneOfAKind}
          aria-label={copy.stockMore}
        >
          <Icon name="add" size={34} />
        </button>
      </div>

      <button
        type="button"
        className={css.toggleRow}
        onClick={() => dispatch({ t: 'oneOfAKind', value: !isOneOfAKind })}
        aria-pressed={isOneOfAKind}
      >
        <span className={`${css.checkbox} ${isOneOfAKind ? css.checkboxOn : ''}`}>
          {isOneOfAKind ? <Icon name="check" size={20} /> : null}
        </span>
        <span className={css.toggleBody}>
          <span className={css.toggleLabel}>{copy.stockOneOfAKind}</span>
        </span>
      </button>
    </ReviewScaffold>
  );
}
