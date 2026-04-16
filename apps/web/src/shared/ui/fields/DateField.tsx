/**
 * DateField - Date display field
 */
import React from 'react';
import styles from './Field.module.css';

export interface DateFieldProps {
  value?: string | Date;
  label?: string;
  editable?: boolean;
  disabled?: boolean;
  format?: 'date' | 'datetime' | 'time';
  onChange?: (value: string) => void;
  className?: string;
}

export function DateField({
  value,
  label,
  editable = false, // Date field is display-only for now
  disabled = false,
  format = 'datetime',
  className = '',
}: DateFieldProps) {
  const formatDate = (dateValue: string | Date | undefined) => {
    if (!dateValue) return '—';
    
    const date = typeof dateValue === 'string' ? new Date(dateValue) : dateValue;
    if (isNaN(date.getTime())) return '—';
    
    const options: Intl.DateTimeFormatOptions = {
      dateStyle: format === 'time' ? undefined : 'medium',
      timeStyle: format === 'date' ? undefined : 'short',
    };
    
    return new Intl.DateTimeFormat('ru-RU', options).format(date);
  };

  return (
    <div className={`${styles.field} ${className}`}>
      {label && (
        <label className={styles.label}>
          {label}
        </label>
      )}
      <div className={styles.dateValue}>
        {formatDate(value)}
      </div>
    </div>
  );
}
