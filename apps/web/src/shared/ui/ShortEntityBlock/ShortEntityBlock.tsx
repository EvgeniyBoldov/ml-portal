/**
 * ShortEntityBlock - Compact entity summary block
 * 
 * Displays brief information about an entity in a card format.
 * Used for showing related entity info (e.g., recommended version).
 */
import React from 'react';
import styles from './ShortEntityBlock.module.css';

export interface ShortEntityBlockItem {
  label: string;
  value: string | number | React.ReactNode;
}

export interface ShortEntityBlockProps {
  /** Block title */
  title: string;
  /** Optional subtitle or badge */
  subtitle?: React.ReactNode;
  /** List of key-value items to display */
  items?: ShortEntityBlockItem[];
  /** Action button text */
  actionLabel?: string;
  /** Action button click handler */
  onAction?: () => void;
  /** Additional class name */
  className?: string;
  /** Children content */
  children?: React.ReactNode;
}

export function ShortEntityBlock({
  title,
  subtitle,
  items,
  actionLabel,
  onAction,
  className,
  children,
}: ShortEntityBlockProps) {
  return (
    <div className={`${styles.block} ${className || ''}`}>
      <div className={styles.header}>
        <span className={styles.title}>{title}</span>
        {subtitle && <span className={styles.subtitle}>{subtitle}</span>}
      </div>

      {items && items.length > 0 && (
        <div className={styles.items}>
          {items.map((item, idx) => (
            <div key={idx} className={styles.item}>
              <span className={styles.itemLabel}>{item.label}:</span>
              <span className={styles.itemValue}>{item.value}</span>
            </div>
          ))}
        </div>
      )}

      {children}

      {actionLabel && onAction && (
        <button className={styles.action} onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}

export default ShortEntityBlock;
