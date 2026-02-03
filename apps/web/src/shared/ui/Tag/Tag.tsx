/**
 * Tag component - displays a tag/label with optional remove button
 */
import React from 'react';
import { Icon } from '../Icon';
import styles from './Tag.module.css';

export interface TagProps {
  label: string;
  onRemove?: () => void;
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger';
  size?: 'small' | 'medium';
  className?: string;
}

export const Tag: React.FC<TagProps> = ({
  label,
  onRemove,
  variant = 'default',
  size = 'medium',
  className,
}) => {
  return (
    <div className={`${styles.tag} ${styles[variant]} ${styles[size]} ${className || ''}`}>
      <span className={styles.label}>{label}</span>
      {onRemove && (
        <button
          className={styles.removeButton}
          onClick={onRemove}
          aria-label={`Remove ${label}`}
          type="button"
        >
          <Icon name="x" size={12} />
        </button>
      )}
    </div>
  );
};

export default Tag;
