import { Icon } from './Icon';
import { speak } from '../../util/speech';
import css from './ScreenHeader.module.css';

interface Props {
  title: string;
  subtitle?: string;
}

/**
 * Every screen opens with this. The speaker button matters more than it
 * looks: the app is voice-first for sellers who cannot read the screen, and
 * the web demo keeps the affordance so judges see that design intent.
 */
export function ScreenHeader({ title, subtitle }: Props) {
  return (
    <header className={css.root}>
      <div className={css.titleRow}>
        <h1 className={css.title}>{title}</h1>
        <button
          type="button"
          className={css.speaker}
          onClick={() => speak(subtitle ? `${title}. ${subtitle}` : title)}
          aria-label="Read this screen aloud"
        >
          <Icon name="volume_up" size={32} />
        </button>
      </div>
      {subtitle ? <p className={css.subtitle}>{subtitle}</p> : null}
    </header>
  );
}
