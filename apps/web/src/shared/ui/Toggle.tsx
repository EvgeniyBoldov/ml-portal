/**
 * Toggle - современный переключатель вместо чекбокса
 */
import React from 'react';
import styles from './Toggle.module.css';

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
  description?: string;
  size?: 'small' | 'medium';
}

export function Toggle({
  checked,
  onChange,
  disabled = false,
  label,
  description,
  size = 'medium',
}: ToggleProps) {
  return (
    <label className={`${styles.wrapper} ${disabled ? styles.disabled : ''}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className={styles.input}
      />
      <span className={`${styles.toggle} ${styles[size]} ${checked ? styles.checked : ''}`}>
        <span className={styles.slider} />
      </span>
      {(label || description) && (
        <span className={styles.labelWrapper}>
          {label && <span className={styles.label}>{label}</span>}
          {description && <span className={styles.description}>{description}</span>}
        </span>
      )}
    </label>
  );
}

export default Toggle;
