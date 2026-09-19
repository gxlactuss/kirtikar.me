import type { ReactNode } from 'react';

import { Icon, type IconName } from '../widgets/Icon';
import css from './review.module.css';

interface Props {
  children: ReactNode;
  tone?: 'info' | 'danger' | 'success';
  icon?: IconName;
}

/** The app's InfoPanel: an icon, a tinted box, a sentence. */
export function Panel({ children, tone = 'info', icon }: Props) {
  const toneClass =
    tone === 'danger' ? css.panelDanger : tone === 'success' ? css.panelSuccess : '';
  const glyph: IconName =
    icon ?? (tone === 'danger' ? 'error_outline' : tone === 'success' ? 'check_circle' : 'lightbulb');

  return (
    <div className={`${css.panel} ${toneClass}`}>
      <Icon name={glyph} size={22} className={css.panelIcon} />
      <span>{children}</span>
    </div>
  );
}
