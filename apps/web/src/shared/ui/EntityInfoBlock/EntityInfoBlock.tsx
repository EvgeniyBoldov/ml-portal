/**
 * EntityInfoBlock - Reusable entity information display component
 * 
 * Shows entity metadata with editable fields
 * Uses flexbox layout for proper alignment
 * Used across Prompt, Baseline, Policy, Tool, etc.
 */
import React from 'react';
import { ContentBlock, type FieldDefinition } from '../ContentBlock/ContentBlock';
import { StatusBlock, type EntityType } from '../StatusBlock/StatusBlock';
import { CompactStatusBlock } from '../CompactStatusBlock/CompactStatusBlock';
import styles from './EntityInfoBlock.module.css';

export interface EntityInfo {
  slug: string;
  name: string;
  description?: string;
  type?: string;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface EntityInfoBlockProps {
  /** Entity data */
  entity: EntityInfo;
  /** Entity type */
  entityType: EntityType;
  /** Editable mode */
  editable?: boolean;
  /** Field definitions */
  fields?: FieldDefinition[];
  /** On field change */
  onFieldChange?: (key: string, value: any) => void;
  /** Show status block */
  showStatus?: boolean;
  /** Status value for status block */
  status?: string;
  /** Status version number */
  statusVersion?: number;
  /** Block width */
  width?: '1/3' | '1/2' | '2/3' | 'full';
  /** Compact display mode */
  compact?: boolean;
  /** Additional CSS class */
  className?: string;
  /** Additional header actions (e.g. status badge) */
  headerActions?: React.ReactNode;
}

export function EntityInfoBlock({
  entity,
  entityType,
  editable = false,
  fields,
  onFieldChange,
  showStatus = false,
  status,
  statusVersion,
  width = 'full',
  compact = false,
  className = '',
  headerActions,
}: EntityInfoBlockProps) {
  // Default fields if not provided
  const defaultFields: FieldDefinition[] = [
    { key: 'slug', label: 'Slug', type: 'text', required: true },
    { key: 'name', label: 'Название', type: 'text', required: true },
    { key: 'description', label: 'Описание', type: 'textarea' },
  ];

  const entityFields = fields || defaultFields;

  if (compact) {
    return (
      <div className={`${styles.entityInfoBlock} ${styles.compact} ${className}`}>
        <ContentBlock
          width={width}
          title="Основная информация"
          editable={editable}
          fields={entityFields}
          data={entity}
          onChange={onFieldChange}
          headerActions={headerActions}
        />
        {showStatus && status && (
          <StatusBlock
            status={status}
            entityType={entityType}
            version={statusVersion}
            compact={true}
            width="full"
          />
        )}
      </div>
    );
  }

  return (
    <div className={`${styles.entityInfoBlock} ${className}`}>
      {/* Main entity info */}
      <div className={styles.entityInfoContent}>
        <ContentBlock
          title="Основная информация"
          editable={editable}
          fields={entityFields}
          data={entity}
          onChange={onFieldChange}
          headerActions={headerActions}
        />
      </div>

      {/* Status block in separate column */}
      {showStatus && status && (
        <div className={styles.statusContent}>
          <StatusBlock
            status={status}
            entityType={entityType}
            version={statusVersion}
          />
        </div>
      )}
    </div>
  );
}

export default EntityInfoBlock;
