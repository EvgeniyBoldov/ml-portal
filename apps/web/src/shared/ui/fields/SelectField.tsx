/**
 * SelectField - Dropdown select field
 */
import React from 'react';
import { Select } from '../Select';
import styles from './Field.module.css';

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectFieldProps {
  value?: string;
  label?: string;
  placeholder?: string;
  options?: SelectOption[];
  editable?: boolean;
  disabled?: boolean;
  required?: boolean;
  onChange?: (value: string) => void;
  className?: string;
}

export function SelectField({
  value = '',
  label,
  placeholder = 'Выберите...',
  options = [],
  editable = true,
  disabled = false,
  required = false,
  onChange,
  className = '',
}: SelectFieldProps) {
  const isDisabled = !editable || disabled;

  // Добавляем пустой опшен если не required
  const selectOptions = required ? options : [
    { value: '', label: placeholder },
    ...options,
  ];

  return (
    <div className={`${styles.field} ${className}`}>
      {label && (
        <label className={styles.label}>
          {label}
          {required && <span className={styles.required}>*</span>}
        </label>
      )}
      <Select
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        options={selectOptions}
        disabled={isDisabled}
      />
    </div>
  );
}
