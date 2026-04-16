import { useState, KeyboardEvent } from 'react';
import styles from './Tags.module.css';

interface TagsProps {
  value: string[];
  onChange: (tags: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function Tags({
  value,
  onChange,
  disabled = false,
  placeholder = 'Введите тег и нажмите Enter...',
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
            {tag}
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
              {tag}
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
      <input
        type="text"
        className={styles.input}
        value={draft}
        onChange={e => setDraft(e.target.value.replace(/\s/g, ''))}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
      />
    </div>
  );
}

export default Tags;
