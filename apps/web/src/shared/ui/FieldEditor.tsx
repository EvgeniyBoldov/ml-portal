/**
 * FieldEditor - компонент для редактирования поля коллекции
 */
import React from 'react';
import Toggle from './Toggle';
import styles from './FieldEditor.module.css';

interface FieldEditorProps {
  name: string;
  type: string;
  required: boolean;
  searchModes: string[];
  onNameChange: (name: string) => void;
  onTypeChange: (type: string) => void;
  onRequiredChange: (required: boolean) => void;
  onSearchModeToggle: (mode: string) => void;
  onRemove: () => void;
}

const FIELD_TYPES = [
  { value: 'text', label: 'Text', icon: '📝' },
  { value: 'integer', label: 'Integer', icon: '🔢' },
  { value: 'float', label: 'Float', icon: '💯' },
  { value: 'boolean', label: 'Boolean', icon: '✓' },
  { value: 'date', label: 'Date', icon: '📅' },
  { value: 'datetime', label: 'DateTime', icon: '🕐' },
];

export function FieldEditor({
  name,
  type,
  required,
  searchModes,
  onNameChange,
  onTypeChange,
  onRequiredChange,
  onSearchModeToggle,
  onRemove,
}: FieldEditorProps) {
  const isTextField = type === 'text';
  const isNumericOrDate = ['integer', 'float', 'datetime', 'date'].includes(type);
  const hasLike = searchModes.includes('like');

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.mainInfo}>
          <input
            type="text"
            className={styles.nameInput}
            value={name}
            onChange={(e) =>
              onNameChange(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))
            }
            placeholder="field_name"
          />
          <div className={styles.typeSelector}>
            {FIELD_TYPES.map((t) => (
              <button
                key={t.value}
                type="button"
                className={`${styles.typeBtn} ${type === t.value ? styles.active : ''}`}
                onClick={() => onTypeChange(t.value)}
                title={t.label}
              >
                <span className={styles.typeIcon}>{t.icon}</span>
                <span className={styles.typeLabel}>{t.label}</span>
              </button>
            ))}
          </div>
        </div>
        <button
          type="button"
          className={styles.removeBtn}
          onClick={onRemove}
          title="Remove field"
        >
          ×
        </button>
      </div>

      <div className={styles.body}>
        <div className={styles.options}>
          <Toggle
            checked={required}
            onChange={onRequiredChange}
            label="Required"
            description="Field must have a value"
            size="small"
          />
        </div>

        <div className={styles.searchSection}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTitle}>Search Modes</span>
            <span className={styles.sectionHint}>Exact search always enabled</span>
          </div>

          <div className={styles.searchModes}>
            {isTextField && (
              <Toggle
                checked={hasLike}
                onChange={() => onSearchModeToggle('like')}
                label="Full-text Search"
                description="Enable LIKE queries for partial matching"
                size="small"
              />
            )}

            {isTextField && hasLike && (
              <Toggle
                checked={searchModes.includes('vector')}
                onChange={() => onSearchModeToggle('vector')}
                label="Vector Search"
                description="Enable semantic search with embeddings"
                size="small"
              />
            )}

            {isNumericOrDate && (
              <Toggle
                checked={searchModes.includes('range')}
                onChange={() => onSearchModeToggle('range')}
                label="Range Search"
                description="Enable queries like >, <, BETWEEN"
                size="small"
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default FieldEditor;
