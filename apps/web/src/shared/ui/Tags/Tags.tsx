import { useState, KeyboardEvent } from 'react';
import styles from './Tags.module.css';

interface TagsProps {
  value: string[];
  onChange: (tags: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
  options?: Array<{ value: string; label: string }>;
}

export function Tags({
  value,
  onChange,
  disabled = false,
  placeholder = 'Введите тег и нажмите Enter...',
  options,
}: TagsProps) {
  const tags = Array.isArray(value) ? value : [];
  const [draft, setDraft] = useState('');

  const addTag = () => {
    const tag = draft.trim();
    if (tag && !tags.includes(tag)) {
      onChange([...tags, tag]);
    }
    setDraft('');
  };

  const labelFor = (tag: string) => options?.find(option => option.value === tag)?.label ?? tag;

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addTag();
    }
    // Block space
    if (e.key === ' ') {
      e.preventDefault();
    }
  };

  // View mode
  if (disabled) {
    if (tags.length === 0) return <span className={styles.empty}>—</span>;
    return (
      <div className={styles.badges}>
        {tags.map((tag, i) => (
          <span key={tag} className={`${styles.badge} ${styles[`tone-${i % 5}`]}`}>
            {labelFor(tag)}
          </span>
        ))}
      </div>
    );
  }

  // Edit mode
  return (
    <div className={styles.editWrap}>
      {tags.length > 0 && (
        <div className={styles.badges}>
          {tags.map((tag, i) => (
            <span key={tag} className={`${styles.badge} ${styles[`tone-${i % 5}`]}`}>
              {labelFor(tag)}
              <button
                type="button"
                className={styles.remove}
                onClick={() => onChange(tags.filter(t => t !== tag))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      {options ? (
        <select
          className={styles.input}
          value=""
          aria-label={placeholder}
          onChange={event => {
            const selected = event.target.value;
            if (selected && !tags.includes(selected)) onChange([...tags, selected]);
          }}
        >
          <option value="" disabled>{placeholder}</option>
          {options.filter(option => !tags.includes(option.value)).map(option => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      ) : (
        <input
          type="text"
          className={styles.input}
          value={draft}
          onChange={e => setDraft(e.target.value.replace(/\s/g, ''))}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
        />
      )}
    </div>
  );
}

export default Tags;
