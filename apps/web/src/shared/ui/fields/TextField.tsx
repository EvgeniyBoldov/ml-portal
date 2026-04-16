/**
 * TextField - Basic text input field
 */
import React from 'react';
import Input from '../Input';
import styles from './Field.module.css';

export interface TextFieldProps {
  value?: string;
  label?: string;
  placeholder?: string;
  editable?: boolean;
  disabled?: boolean;
  required?: boolean;
  onChange?: (value: string) => void;
  className?: string;
}

export function TextField({
  value = '',
  label,
  placeholder,
  editable = true,
  disabled = false,
  required = false,
  onChange,
  className = '',
}: TextFieldProps) {
  const isDisabled = !editable || disabled;

  return (
    <div className={`${styles.field} ${className}`}>
      {label && (
        <label className={styles.label}>
          {label}
          {required && <span className={styles.required}>*</span>}
        </label>
      )}
      <Input
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder={placeholder}
        disabled={isDisabled}
      />
    </div>
  );
}
