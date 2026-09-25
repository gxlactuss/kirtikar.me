import type { ReactNode } from 'react';

import { Icon, type IconName } from '../widgets/Icon';
import css from './result.module.css';

interface Props {
  children: ReactNode;
  tone?: 'info' | 'danger';
  icon?: IconName;
}

/** The app's InfoPanel: an icon, a tinted box, a sentence. */
export function Panel({ children, tone = 'info', icon }: Props) {
  const glyph: IconName = icon ?? (tone === 'danger' ? 'error_outline' : 'lightbulb');
  return (
    <div className={`${css.panel} ${tone === 'danger' ? css.panelDanger : ''}`}>
      <Icon name={glyph} size={22} className={css.panelIcon} />
      <span>{children}</span>
    </div>
  );
}
