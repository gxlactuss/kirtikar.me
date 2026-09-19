import { Icon, type IconName } from './Icon';
import css from './SuccessMark.module.css';

interface Props {
  icon?: IconName;
  tone?: 'success' | 'danger';
}

/** The celebration mark shown when something has landed. */
export function SuccessMark({ icon = 'check', tone = 'success' }: Props) {
  return (
    <div className={`${css.root} ${tone === 'danger' ? css.danger : ''}`}>
      <span className={css.circle} />
      <span className={css.ring} />
      <span className={css.icon}>
        <Icon name={icon} size={64} />
      </span>
    </div>
  );
}
