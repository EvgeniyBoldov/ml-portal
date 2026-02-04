/**
 * StatusBlock - Reusable status display component for entities
 * 
 * Shows entity status with badge, actions, and metadata
 * Used across Prompt, Baseline, Policy, Tool, etc.
 */
import React from 'react';
import Badge from '../Badge';
import Button from '../Button';
import { ContentBlock, type FieldDefinition } from '../ContentBlock/ContentBlock';
import { useStatusConfig } from '@/shared/hooks/useStatusConfig';
import styles from './StatusBlock.module.css';

export type EntityType = 'prompt' | 'baseline' | 'policy';

export interface StatusBlockProps {
  /** Entity status value */
  status: string;
  /** Entity type for status configuration */
  entityType: EntityType;
  /** Entity version number */
  version?: number;
  /** Show actions for status changes */
  showActions?: boolean;
  /** Actions available for current status */
  actions?: Array<{
    label: string;
    variant?: 'primary' | 'secondary' | 'ghost';
    onClick: () => void;
    disabled?: boolean;
  }>;
  /** Additional metadata fields */
  metadata?: Array<{
    label: string;
    value: string | number;
  }>;
  /** Block width */
  width?: '1/3' | '1/2' | '2/3' | 'full';
  /** Compact display mode */
  compact?: boolean;
  /** Additional CSS class */
  className?: string;
}

export function StatusBlock({
  status,
  entityType,
  version,
  showActions = false,
  actions = [],
  metadata = [],
  width = 'full',
  compact = false,
  className = '',
}: StatusBlockProps) {
  const statusConfig = useStatusConfig(entityType);
  
  const statusBadge = (
    <Badge tone={statusConfig.tones[status]}>
      {statusConfig.labels[status]}
    </Badge>
  );

  if (compact) {
    return (
      <div className={`${styles.statusBlock} ${styles.compact} ${className}`}>
        <div className={styles.statusHeader}>
          {version && <span className={styles.version}>v{version}</span>}
          {statusBadge}
        </div>
        {showActions && actions.length > 0 && (
          <div className={styles.actions}>
            {actions.map((action, index) => (
              <Button
                key={index}
                size="small"
                variant={action.variant || 'ghost'}
                onClick={action.onClick}
                disabled={action.disabled}
              >
                {action.label}
              </Button>
            ))}
          </div>
        )}
      </div>
    );
  }

  const metadataFields: FieldDefinition[] = metadata.map(item => ({
    key: item.label,
    label: item.label,
    type: 'text' as const,
    value: item.value,
  }));

  return (
    <ContentBlock
      width={width}
      title={version ? `Версия v${version}` : 'Статус'}
      headerActions={statusBadge}
      className={className}
    >
      <div className={styles.statusContent}>
        {metadataFields.length > 0 && (
          <div className={styles.metadata}>
            {metadataFields.map((field) => (
              <div key={field.key} className={styles.metadataItem}>
                <span className={styles.metadataLabel}>{field.label}:</span>
                <span className={styles.metadataValue}>{field.value}</span>
              </div>
            ))}
          </div>
        )}
        
        {showActions && actions.length > 0 && (
          <div className={styles.actions}>
            {actions.map((action, index) => (
              <Button
                key={index}
                variant={action.variant || 'primary'}
                onClick={action.onClick}
                disabled={action.disabled}
              >
                {action.label}
              </Button>
            ))}
          </div>
        )}
      </div>
    </ContentBlock>
  );
}

export default StatusBlock;
