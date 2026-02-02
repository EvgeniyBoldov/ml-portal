/**
 * StatusBadgeCard - Compact status display card
 * 
 * A simple card showing status label and badge, not based on ContentBlock.
 * Does not stretch to fill available space.
 */
import React from 'react';
import { Select } from '../Select';
import Badge from '../Badge';
import styles from './StatusBadgeCard.module.css';

export interface StatusOption {
  value: string;
  label: string;
  tone?: 'neutral' | 'success' | 'warn' | 'danger' | 'info';
}

export type StatusBadgeCardWidth = '1/3' | '1/2' | '2/3' | 'full';

export interface StatusBadgeCardProps {
  /** Label text (default: "Статус") */
  label?: string;
  /** Current status value */
  status: string;
  /** Status options */
  statusOptions: StatusOption[];
  /** Is status editable (dropdown vs badge) */
  editable?: boolean;
  /** Status change handler */
  onStatusChange?: (status: string) => void;
  /** Width in grid (1/3, 1/2, 2/3, full) */
  width?: StatusBadgeCardWidth;
  /** Additional CSS class */
  className?: string;
}

const STATUS_TONES: Record<string, 'neutral' | 'success' | 'warn' | 'danger' | 'info'> = {
  draft: 'warn',
  active: 'success',
  inactive: 'neutral',
  archived: 'neutral',
};

const widthToSpan: Record<StatusBadgeCardWidth, number> = {
  '1/3': 4,
  '1/2': 6,
  '2/3': 8,
  'full': 12,
};

export function StatusBadgeCard({
  label = 'Статус',
  status,
  statusOptions,
  editable = false,
  onStatusChange,
  width,
  className = '',
}: StatusBadgeCardProps) {
  const currentOption = statusOptions.find(o => o.value === status);
  const tone = currentOption?.tone || STATUS_TONES[status] || 'neutral';
  const spanClass = width ? `span-${widthToSpan[width]}` : '';

  return (
    <div className={`${styles.card} ${spanClass ? styles[spanClass] : ''} ${className}`}>
      <span className={styles.label}>{label}</span>
      {editable ? (
        <Select
          value={status}
          onChange={(val) => onStatusChange?.(val)}
          options={statusOptions.map(o => ({ value: o.value, label: o.label }))}
          className={styles.select}
        />
      ) : (
        <Badge tone={tone}>
          {currentOption?.label || status}
        </Badge>
      )}
    </div>
  );
}

export default StatusBadgeCard;
