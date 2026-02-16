import { useState, KeyboardEvent } from 'react';
import Input from '../Input';
import Button from '../Button';
import { Tag } from '../Tag';
import styles from './TagsInput.module.css';

interface TagsInputProps {
  value: string[];
  onChange: (tags: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
  maxTags?: number;
}

export function TagsInput({
  value,
  onChange,
  disabled = false,
  placeholder = 'Добавить тег и нажать Enter',
  maxTags,
}: TagsInputProps) {
  const [draft, setDraft] = useState('');

  const canAddMore = maxTags === undefined || value.length < maxTags;

  const addTag = () => {
    const nextTag = draft.trim();
    if (!nextTag || !canAddMore) {
      return;
    }
    if (value.includes(nextTag)) {
      setDraft('');
      return;
    }
    onChange([...value, nextTag]);
    setDraft('');
  };

  const removeTag = (tag: string) => {
    onChange(value.filter((item) => item !== tag));
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      addTag();
    }
  };

  return (
    <div className={styles['tags-input']}>
      <div className={styles['tags-list']}>
        {value.map((tag) => (
          <Tag
            key={tag}
            label={tag}
            variant="default"
            size="small"
            onRemove={disabled ? undefined : () => removeTag(tag)}
          />
        ))}
      </div>

      <div className={styles['controls-row']}>
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || !canAddMore}
        />
        <Button type="button" variant="outline" onClick={addTag} disabled={disabled || !canAddMore || !draft.trim()}>
          Добавить
        </Button>
      </div>
    </div>
  );
}

export default TagsInput;
