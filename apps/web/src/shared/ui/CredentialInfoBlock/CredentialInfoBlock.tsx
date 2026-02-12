/**
 * CredentialInfoBlock - Specialized info block for credentials
 * 
 * Similar to EntityInfoBlock but adapted for credential schema:
 * - instance_id instead of slug/name
 * - auth_type instead of type
 * - No description field
 */
import React from 'react';
import { ContentBlock, type FieldDefinition } from '../ContentBlock/ContentBlock';
import { StatusBlock, type EntityType } from '../StatusBlock/StatusBlock';
import styles from './CredentialInfoBlock.module.css';

export interface CredentialInfo {
  id: string;
  instance_id: string;
  auth_type: string;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CredentialInfoBlockProps {
  /** Credential data */
  credential: CredentialInfo;
  /** Entity type for status block */
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
  /** Additional CSS class */
  className?: string;
  /** Additional header actions (e.g. status badge) */
  headerActions?: React.ReactNode;
}

export function CredentialInfoBlock({
  credential,
  entityType,
  editable = false,
  fields,
  onFieldChange,
  showStatus = false,
  status,
  statusVersion,
  width = 'full',
  className = '',
  headerActions,
}: CredentialInfoBlockProps) {
  // Default fields if not provided
  const defaultFields: FieldDefinition[] = [
    { key: 'instance_id', label: 'Инстанс', type: 'select', required: true },
    { key: 'auth_type', label: 'Тип авторизации', type: 'select', required: true },
    { key: 'is_active', label: 'Статус', type: 'boolean' },
    { key: 'created_at', label: 'Создан', type: 'date' },
  ];

  const credentialFields = fields || defaultFields;

  return (
    <div className={`${styles.credentialInfoBlock} ${className}`}>
      <ContentBlock
        width={width}
        title="Основные настройки"
        editable={editable}
        fields={credentialFields}
        data={credential}
        onChange={onFieldChange}
        headerActions={headerActions}
      />
      {showStatus && status && (
        <StatusBlock
          status={status}
          entityType={entityType}
          version={statusVersion}
        />
      )}
    </div>
  );
}
