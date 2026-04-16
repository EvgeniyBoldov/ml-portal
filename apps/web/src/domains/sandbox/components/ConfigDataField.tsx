import type { ChangeEvent } from 'react';
import Toggle from '@/shared/ui/Toggle';
import { Select, type SelectOption } from '@/shared/ui/Select';
import styles from './ConfigDataField.module.css';

export type SandboxConfigFieldType = 'tags' | 'select' | 'json' | 'text' | 'integer' | 'float' | 'boolean';

export interface SandboxConfigField {
  name: string;
  type: SandboxConfigFieldType;
  value: unknown;
  label?: string;
  editable?: boolean;
  options?: string[];
}

interface Props {
  field: SandboxConfigField;
  displayName?: string;
  tooltipText?: string;
  inputValue: string;
  defaultValue: string;
  selectOptions?: SelectOption[];
  status: 'default' | 'dirty' | 'overridden';
  readOnly: boolean;
  onChange: (value: string) => void;
  onCommitValue: (value: string) => void;
  onClear: () => void;
  onUseDefault: () => void;
}

export default function ConfigDataField({
  field,
  displayName,
  tooltipText,
  inputValue,
  defaultValue,
  selectOptions = [],
  status,
  readOnly,
  onChange,
  onCommitValue,
  onClear,
  onUseDefault,
}: Props) {
  const isWide = field.type === 'text' || field.type === 'json';
  const isNumeric = field.type === 'integer' || field.type === 'float';
  const normalizedInputValue = inputValue.length > 0 ? inputValue : defaultValue;
  const statusClass =
    status === 'overridden'
      ? styles['field-overridden']
      : status === 'dirty'
        ? styles['field-dirty']
        : styles['field-default'];

  const inputProps = {
    value: inputValue,
    placeholder: defaultValue,
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(event.target.value),
    disabled: readOnly,
  };

  const renderInput = () => {
    if (field.type === 'boolean') {
      return (
        <div className={styles['toggle-wrap']}>
          <Toggle
            checked={normalizedInputValue.trim().toLowerCase() === 'true'}
            onChange={(checked) => {
              const nextValue = String(checked);
              onChange(nextValue);
              onCommitValue(nextValue);
            }}
            disabled={readOnly}
            label={normalizedInputValue.trim().toLowerCase() === 'true' ? 'true' : 'false'}
          />
        </div>
      );
    }

    if (field.type === 'select') {
      return (
        <Select
          options={selectOptions}
          value={normalizedInputValue}
          onChange={(value) => {
            onChange(value);
            onCommitValue(value);
          }}
          disabled={readOnly || selectOptions.length === 0}
          placeholder={defaultValue || 'Выберите значение'}
        />
      );
    }

    if (field.type === 'tags') {
      return (
        <input
          className={styles['value-input']}
          type="text"
          value={inputValue}
          placeholder={defaultValue}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              onCommitValue(event.currentTarget.value);
            }
          }}
          disabled={readOnly}
        />
      );
    }

    if (isWide) {
      return (
        <textarea
          className={styles['value-input-wide']}
          rows={field.type === 'json' ? 6 : 4}
          {...inputProps}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              onCommitValue(event.currentTarget.value);
            }
          }}
        />
      );
    }

    return (
      <input
        className={styles['value-input']}
        type={isNumeric ? 'number' : 'text'}
        {...inputProps}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            onCommitValue(event.currentTarget.value);
          }
        }}
      />
    );
  };

  return (
    <div className={`${styles.field} ${isWide ? styles['field-wide'] : styles['field-short']} ${statusClass}`}>
      <div className={styles['field-head']}>
        <div className={styles['field-label-row']}>
          <div className={styles['field-name']} title={tooltipText}>{displayName ?? field.name}</div>
          {!readOnly ? (
            <div className={styles['field-tools']}>
              <button
                type="button"
                className={styles['icon-btn']}
                onClick={onClear}
                aria-label="Очистить поле"
                title="Очистить поле"
              >
                ×
              </button>
              <button
                type="button"
                className={styles['icon-btn']}
                onClick={onUseDefault}
                aria-label="Скопировать значение по умолчанию"
                title="Скопировать значение по умолчанию"
              >
                ⧉
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {renderInput()}
    </div>
  );
}
