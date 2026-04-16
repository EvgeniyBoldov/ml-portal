/**
 * TextareaField - Multi-line text input field
 */
import React from 'react';
import Textarea from '../Textarea';
import styles from './Field.module.css';

export interface TextareaFieldProps {
  value?: string;
  label?: string;
  placeholder?: string;
  rows?: number;
  editable?: boolean;
  disabled?: boolean;
  required?: boolean;
  onChange?: (value: string) => void;
  className?: string;
}

export function TextareaField({
  value = '',
  label,
  placeholder,
  rows = 3,
  editable = true,
  disabled = false,
  required = false,
  onChange,
  className = '',
}: TextareaFieldProps) {
  const isDisabled = !editable || disabled;

  return (
    <div className={`${styles.field} ${className}`}>
      {label && (
        <label className={styles.label}>
          {label}
          {required && <span className={styles.required}>*</span>}
        </label>
      )}
      <Textarea
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        disabled={isDisabled}
      />
    </div>
  );
}
