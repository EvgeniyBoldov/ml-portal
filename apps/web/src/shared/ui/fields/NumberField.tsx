/**
 * NumberField - Numeric input field
 */
import React from 'react';
import Input from '../Input';
import styles from './Field.module.css';

export interface NumberFieldProps {
  value?: number;
  label?: string;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
  editable?: boolean;
  disabled?: boolean;
  required?: boolean;
  onChange?: (value: number) => void;
  className?: string;
}

export function NumberField({
  value = 0,
  label,
  placeholder,
  min,
  max,
  step,
  editable = true,
  disabled = false,
  required = false,
  onChange,
  className = '',
}: NumberFieldProps) {
  const isDisabled = !editable || disabled;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const numValue = parseFloat(e.target.value);
    if (!isNaN(numValue)) {
      onChange?.(numValue);
    }
  };

  return (
    <div className={`${styles.field} ${className}`}>
      {label && (
        <label className={styles.label}>
          {label}
          {required && <span className={styles.required}>*</span>}
        </label>
      )}
      <Input
        type="number"
        value={value}
        onChange={handleChange}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        disabled={isDisabled}
      />
    </div>
  );
}
