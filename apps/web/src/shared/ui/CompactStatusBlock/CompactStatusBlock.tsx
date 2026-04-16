/**
 * CompactStatusBlock - Status display without header
 * 
 * Like a compact entity status block - label and value inline.
 * Used in tool, agent and other compact status displays.
 */
import React from 'react';
import Badge from '../Badge';
import styles from './CompactStatusBlock.module.css';

export interface CompactStatusBlockProps {
  /** Status label */
  label: string;
  /** Status value */
  value: string;
  /** Status tone for badge */
  tone?: 'info' | 'success' | 'warn' | 'danger' | 'neutral';
  /** Show as inline block */
  inline?: boolean;
  /** Additional CSS class */
  className?: string;
}

export function CompactStatusBlock({
  label,
  value,
  tone = 'neutral',
  inline = false,
  className = '',
}: CompactStatusBlockProps) {
  return (
    <div className={`${styles.compactStatusBlock} ${inline ? styles.inline : ''} ${className}`}>
      <span className={styles.label}>{label}:</span>
      <Badge tone={tone} size="sm">{value}</Badge>
    </div>
  );
}

export default CompactStatusBlock;
