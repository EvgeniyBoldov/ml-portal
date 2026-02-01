/**
 * FormField - Unified form field component for view/edit modes
 * 
 * Same component renders in both modes:
 * - view: input is disabled/readonly
 * - edit: input is editable
 */
import React from 'react';
import styles from './FormField.module.css';

export type FormFieldType = 'text' | 'number' | 'textarea' | 'switch';

export interface FormFieldProps {
  /** Field label */
  label: string;
  /** Field value */
  value: string | number | boolean | null | undefined;
  /** Field type */
  type?: FormFieldType;
  /** Placeholder text */
  placeholder?: string;
  /** Description/hint below the field */
  description?: string;
  /** Is field editable */
  editable?: boolean;
  /** Is field required */
  required?: boolean;
  /** Error message */
  error?: string;
  /** Change handler */
  onChange?: (value: string | number | boolean) => void;
  /** Additional class name */
  className?: string;
}

export function FormField({
  label,
  value,
  type = 'text',
  placeholder,
  description,
  editable = false,
  required = false,
  error,
  onChange,
  className,
}: FormFieldProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (!onChange) return;
    
    if (type === 'number') {
      const num = parseFloat(e.target.value);
      onChange(isNaN(num) ? 0 : num);
    } else {
      onChange(e.target.value);
    }
  };

  const handleSwitchChange = () => {
    if (!onChange) return;
    onChange(!value);
  };

  const displayValue = value === null || value === undefined ? '' : String(value);

  return (
    <div className={`${styles.field} ${className || ''}`}>
      <label className={styles.label}>
        {label}
        {required && <span className={styles.required}>*</span>}
      </label>

      {type === 'switch' ? (
        <div className={styles.switchRow}>
          <button
            type="button"
            role="switch"
            aria-checked={Boolean(value)}
            className={`${styles.switch} ${value ? styles.switchOn : ''}`}
            onClick={editable ? handleSwitchChange : undefined}
            disabled={!editable}
          >
            <span className={styles.switchThumb} />
          </button>
          {description && <span className={styles.switchDescription}>{description}</span>}
        </div>
      ) : type === 'textarea' ? (
        <textarea
          className={`${styles.input} ${styles.textarea} ${error ? styles.error : ''}`}
          value={displayValue}
          placeholder={placeholder}
          onChange={handleChange}
          readOnly={!editable}
          disabled={!editable}
          rows={3}
        />
      ) : (
        <input
          type={type === 'number' ? 'number' : 'text'}
          className={`${styles.input} ${error ? styles.error : ''}`}
          value={displayValue}
          placeholder={placeholder}
          onChange={handleChange}
          readOnly={!editable}
          disabled={!editable}
        />
      )}

      {description && type !== 'switch' && (
        <span className={styles.description}>{description}</span>
      )}

      {error && <span className={styles.errorText}>{error}</span>}
    </div>
  );
}

export default FormField;
