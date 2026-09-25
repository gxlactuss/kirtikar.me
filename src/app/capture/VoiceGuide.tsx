import { copy } from '../../copy/en';
import { Icon } from '../widgets/Icon';
import css from './voice.module.css';

/** The app's `_GuidePanel`: what a seller can mention in the voice note. */
export function VoiceGuide() {
  return (
    <div className={css.guide}>
      <p className={css.guideTitle}>
        <Icon name="lightbulb" size={24} className={css.guideIcon} />
        {copy.voiceGuideTitle}
      </p>
      <ul className={css.guideList}>
        {copy.voiceGuidePoints.map((point) => (
          <li key={point}>{point}</li>
        ))}
      </ul>
    </div>
  );
}
