import { useState } from 'react';

import { copy } from '../../copy/en';
import { Icon } from '../widgets/Icon';
import css from './review.module.css';

interface Props {
  label: string;
  value: string | null;
  onSave: (value: string | null) => void;
}

/**
 * One row of the fact sheet, editable in place.
 *
 * "Press anything that is wrong" is the app's instruction, so the whole row
 * is the tap target rather than a separate pencil button — a seller who
 * cannot read the label can still press the thing that looks wrong.
 */
export function FieldCard({ label, value, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? '');

  if (editing) {
    const commit = () => {
      const next = draft.trim();
      onSave(next.length ? next : null);
      setEditing(false);
    };
    return (
      <div className={css.editRow}>
        <input
          className={css.editInput}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={copy.correctTypeHint}
          aria-label={label}
          autoFocus
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') setEditing(false);
          }}
        />
        <button
          type="button"
          className={css.editSave}
          onClick={commit}
          aria-label={`Save ${label}`}
        >
          <Icon name="check" size={28} />
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      className={css.field}
      onClick={() => {
        setDraft(value ?? '');
        setEditing(true);
      }}
    >
      <span className={css.fieldBody}>
        <span className={css.fieldLabel}>{label}</span>
        <span className={`${css.fieldValue} ${value ? '' : css.fieldEmpty}`}>
          {value ?? copy.notSaid}
        </span>
      </span>
      <Icon name="edit" size={24} className={css.fieldIcon} />
    </button>
  );
}
