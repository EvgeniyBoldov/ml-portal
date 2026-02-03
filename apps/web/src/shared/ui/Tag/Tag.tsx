/**
 * Tag component - displays a tag/label with optional remove button
 * Supports auto-coloring like TagBadge
 */
import React from 'react';
import { Icon } from '../Icon';
import styles from './Tag.module.css';

// Simple hash function for deterministic colors (from TagBadge)
const hashString = (str: string): number => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash);
};

// Auto-color palette (from TagBadge)
const getAutoColor = (label: string) => {
  const hash = hashString(label);
  const colors = [
    { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-200' },
    { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-200' },
    { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-200' },
    { bg: 'bg-purple-100', text: 'text-purple-800', border: 'border-purple-200' },
    { bg: 'bg-pink-100', text: 'text-pink-800', border: 'border-pink-200' },
    { bg: 'bg-indigo-100', text: 'text-indigo-800', border: 'border-indigo-200' },
    { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-200' },
    { bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-200' },
    { bg: 'bg-teal-100', text: 'text-teal-800', border: 'border-teal-200' },
    { bg: 'bg-cyan-100', text: 'text-cyan-800', border: 'border-cyan-200' },
  ];
  return colors[hash % colors.length];
};

export interface TagProps {
  label: string;
  onRemove?: () => void;
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'auto';
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
  const autoColor = variant === 'auto' ? getAutoColor(label) : null;
  
  return (
    <div 
      className={`${styles.tag} ${styles[variant]} ${styles[size]} ${
        autoColor ? styles.autoColor : ''
      } ${className || ''}`}
      style={
        autoColor
          ? {
              backgroundColor: autoColor.bg.replace('bg-', '').replace('-100', ''),
              color: autoColor.text.replace('text-', '').replace('-800', ''),
              borderColor: autoColor.border.replace('border-', '').replace('-200', ''),
            }
          : undefined
      }
    >
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
