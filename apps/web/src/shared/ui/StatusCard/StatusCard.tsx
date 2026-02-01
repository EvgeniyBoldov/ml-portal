/**
 * StatusCard - Card with status dropdown and optional actions
 * 
 * Extends ContentBlock with status-specific functionality:
 * - Status badge/dropdown
 * - Action buttons based on status
 */
import React from 'react';
import { ContentBlock, type BlockWidth } from '../ContentBlock';
import { Select } from '../Select';
import Badge from '../Badge';
import Button from '../Button';
import styles from './StatusCard.module.css';

export interface StatusOption {
  value: string;
  label: string;
  tone?: 'neutral' | 'success' | 'warn' | 'danger' | 'info';
}

export interface StatusAction {
  label: string;
  onClick: () => void;
  variant?: 'primary' | 'secondary' | 'outline' | 'danger';
  disabled?: boolean;
  /** Show only for specific statuses */
  showFor?: string[];
  /** Hide for specific statuses */
  hideFor?: string[];
}

export interface StatusCardProps {
  /** Card title (optional, if not provided only status is shown) */
  title?: string;
  /** Card width */
  width?: BlockWidth;
  /** Current status value */
  status: string;
  /** Status options for dropdown */
  statusOptions: StatusOption[];
  /** Is status editable (dropdown vs badge) */
  editable?: boolean;
  /** Status change handler */
  onStatusChange?: (status: string) => void;
  /** Action buttons */
  actions?: StatusAction[];
  /** Card content */
  children?: React.ReactNode;
  /** Additional CSS class */
  className?: string;
}

const STATUS_TONES: Record<string, 'neutral' | 'success' | 'warn' | 'danger' | 'info'> = {
  draft: 'warn',
  active: 'success',
  inactive: 'neutral',
  archived: 'neutral',
};

export function StatusCard({
  title,
  width = 'full',
  status,
  statusOptions,
  editable = false,
  onStatusChange,
  actions = [],
  children,
  className = '',
}: StatusCardProps) {
  const currentOption = statusOptions.find(o => o.value === status);
  const tone = currentOption?.tone || STATUS_TONES[status] || 'neutral';

  // Filter actions based on current status
  const visibleActions = actions.filter(action => {
    if (action.showFor && !action.showFor.includes(status)) return false;
    if (action.hideFor && action.hideFor.includes(status)) return false;
    return true;
  });

  // Compact mode: header-only style (like version block)
  if (!title) {
    return (
      <ContentBlock
        width={width}
        title="Статус"
        headerActions={
          editable ? (
            <Select
              value={status}
              onChange={(val) => onStatusChange?.(val)}
              options={statusOptions.map(o => ({ value: o.value, label: o.label }))}
              className={styles.statusSelect}
            />
          ) : (
            <Badge tone={tone}>
              {currentOption?.label || status}
            </Badge>
          )
        }
        className={className}
      />
    );
  }

  // Full mode: with title and header actions
  const renderHeaderActions = () => (
    <div className={styles.headerActions}>
      {editable ? (
        <Select
          value={status}
          onChange={(val) => onStatusChange?.(val)}
          options={statusOptions.map(o => ({ value: o.value, label: o.label }))}
          className={styles.statusSelect}
        />
      ) : (
        <Badge tone={tone}>
          {currentOption?.label || status}
        </Badge>
      )}
      {visibleActions.map((action, idx) => (
        <Button
          key={idx}
          variant={action.variant || 'secondary'}
          size="sm"
          onClick={action.onClick}
          disabled={action.disabled}
        >
          {action.label}
        </Button>
      ))}
    </div>
  );

  return (
    <ContentBlock
      width={width}
      title={title}
      headerActions={renderHeaderActions()}
      className={className}
    >
      {children}
    </ContentBlock>
  );
}

export default StatusCard;
