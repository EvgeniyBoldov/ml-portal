/**
 * MetaRow - Simple label: value display component
 * 
 * Replaces inline styles for metadata display
 */
import React from 'react';
import styles from './MetaRow.module.css';

export interface MetaRowProps {
  label: string;
  value: React.ReactNode;
  className?: string;
}

export function MetaRow({ label, value, className = '' }: MetaRowProps) {
  return (
    <div className={`${styles.metaRow} ${className}`}>
      <span className={styles.metaLabel}>{label}</span>
      <span className={styles.metaValue}>{value}</span>
    </div>
  );
}

export interface MetaListProps {
  items: Array<{ label: string; value: React.ReactNode }>;
  className?: string;
}

export function MetaList({ items, className = '' }: MetaListProps) {
  return (
    <div className={`${styles.metaList} ${className}`}>
      {items.map((item, index) => (
        <MetaRow key={index} label={item.label} value={item.value} />
      ))}
    </div>
  );
}

export default MetaRow;
