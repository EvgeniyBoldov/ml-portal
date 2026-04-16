/**
 * CodeField - Code display/input field
 */
import React from 'react';
import Input from '../Input';
import styles from './Field.module.css';

export interface CodeFieldProps {
  value?: string;
  label?: string;
  placeholder?: string;
  editable?: boolean;
  disabled?: boolean;
  onChange?: (value: string) => void;
  className?: string;
}

export function CodeField({
  value = '',
  label,
  placeholder,
  editable = true,
  disabled = false,
  onChange,
  className = '',
}: CodeFieldProps) {
  const isDisabled = !editable || disabled;

  return (
    <div className={`${styles.field} ${className}`}>
      {label && (
        <label className={styles.label}>
          {label}
        </label>
      )}
      <Input
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder={placeholder}
        disabled={isDisabled}
        className={styles.codeInput}
      />
    </div>
  );
}
