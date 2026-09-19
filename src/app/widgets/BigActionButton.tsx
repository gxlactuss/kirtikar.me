import { FORWARD_ICONS, Icon, type IconName } from './Icon';
import css from './BigActionButton.module.css';

export type ButtonTone = 'primary' | 'secondary' | 'danger';

interface Props {
  label: string;
  icon: IconName;
  onClick?: () => void;
  tone?: ButtonTone;
  busy?: boolean;
  disabled?: boolean;
  type?: 'button' | 'submit';
}

/**
 * The app's one button. 64px minimum height, 30px icon, 14px gap.
 *
 * Carries the rule from big_action_button.dart:33-48: a PRIMARY button whose
 * icon is check / arrow_forward / play_arrow renders in success green rather
 * than terracotta, because those mean "go". Secondary and danger tones are
 * unaffected. Getting this wrong makes every "next" button the wrong colour.
 */
export function BigActionButton({
  label,
  icon,
  onClick,
  tone = 'primary',
  busy = false,
  disabled = false,
  type = 'button',
}: Props) {
  const isGo = tone === 'primary' && FORWARD_ICONS.has(icon);
  const toneClass = isGo ? css.go : css[tone];

  return (
    <button
      type={type}
      className={`${css.button} ${toneClass}`}
      onClick={onClick}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
    >
      {busy ? <span className={css.spinner} /> : <Icon name={icon} size={30} />}
      <span className={css.label}>{label}</span>
    </button>
  );
}
