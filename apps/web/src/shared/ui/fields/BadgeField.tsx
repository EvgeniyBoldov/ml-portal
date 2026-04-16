/**
 * BadgeField - Display-only badge field
 */
import React from 'react';
import Badge from '../Badge';
import styles from './Field.module.css';

export interface BadgeFieldProps {
  value?: string | number;
  label?: string;
  tone?: 'info' | 'success' | 'warn' | 'danger' | 'neutral';
  editable?: boolean;
  disabled?: boolean;
  className?: string;
}

export function BadgeField({
  value,
  label,
  tone = 'neutral',
  editable = false, // Badge is always display-only
  disabled = false,
  className = '',
}: BadgeFieldProps) {
  return (
    <div className={`${styles.field} ${className}`}>
      {label && (
        <label className={styles.label}>
          {label}
        </label>
      )}
      {value ? (
        <Badge tone={tone}>{String(value)}</Badge>
      ) : (
        <span className={styles.emptyValue}>—</span>
      )}
    </div>
  );
}
