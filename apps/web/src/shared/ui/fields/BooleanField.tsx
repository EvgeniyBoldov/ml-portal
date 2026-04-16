/**
 * BooleanField - Toggle/switch field
 */
import React from 'react';
import Toggle from '../Toggle';
import styles from './Field.module.css';

export interface BooleanFieldProps {
  value?: boolean;
  label?: string;
  editable?: boolean;
  disabled?: boolean;
  onChange?: (checked: boolean) => void;
  className?: string;
}

export function BooleanField({
  value = false,
  label,
  editable = true,
  disabled = false,
  onChange,
  className = '',
}: BooleanFieldProps) {
  const isDisabled = !editable || disabled;

  return (
    <div className={`${styles.field} ${className}`}>
      {label && (
        <label className={styles.label}>
          {label}
        </label>
      )}
      <Toggle
        checked={value}
        onChange={onChange || (() => {})}
        disabled={isDisabled}
      />
    </div>
  );
}
