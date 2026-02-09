/**
 * VersionsBlock - Reusable versions table component
 * 
 * Simple table display for entity versions
 * Used across Prompt, Baseline, Policy, Tool, etc.
 */
import React from 'react';
import Badge from '../Badge';
import DataTable from '../DataTable/DataTable';
import { useStatusConfig } from '@/shared/hooks/useStatusConfig';
import type { DataTableColumn } from '../DataTable/DataTable';
import styles from './VersionsBlock.module.css';

export interface VersionInfo {
  id: string;
  version: number;
  status: string;
  created_at: string;
  updated_at?: string;
  notes?: string;
}

export interface VersionsBlockProps {
  /** Entity type for status configuration */
  entityType: 'prompt' | 'baseline' | 'policy' | 'agent' | 'limit' | 'tool';
  /** Versions data */
  versions: VersionInfo[];
  /** Currently selected version */
  selectedVersion?: VersionInfo;
  /** On version selection */
  onSelectVersion?: (version: VersionInfo) => void;
  /** ID of recommended version */
  recommendedVersionId?: string;
  /** On set as recommended */
  onSetRecommended?: (version: VersionInfo) => void;
  /** Custom columns override */
  columns?: DataTableColumn<VersionInfo>[];
  /** Additional CSS class */
  className?: string;
}

export function VersionsBlock({
  entityType,
  versions,
  selectedVersion,
  onSelectVersion,
  recommendedVersionId,
  onSetRecommended,
  columns: customColumns,
  className = '',
}: VersionsBlockProps) {
  const statusConfig = useStatusConfig(entityType);

  const defaultColumns: DataTableColumn<VersionInfo>[] = [
    {
      key: 'version',
      label: 'Версия',
      render: (v: VersionInfo) => `v${v.version}`,
    },
    {
      key: 'recommended',
      label: 'Основная',
      width: 100,
      render: (v: VersionInfo) => recommendedVersionId && v.id === recommendedVersionId ? (
        <Badge tone="info">Основная</Badge>
      ) : null,
    },
    {
      key: 'status',
      label: 'Статус',
      render: (v: VersionInfo) => (
        <Badge tone={statusConfig.tones[v.status]}>
          {statusConfig.labels[v.status]}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      label: 'Создана',
      render: (v: VersionInfo) => new Date(v.created_at).toLocaleDateString('ru-RU'),
    },
    {
      key: 'updated_at',
      label: 'Обновлена',
      render: (v: VersionInfo) => v.updated_at 
        ? new Date(v.updated_at).toLocaleDateString('ru-RU')
        : '-',
    },
  ];

  const columns = customColumns || defaultColumns;

  return (
    <div className={`${styles.versionsBlock} ${className}`}>
      <DataTable
        data={versions}
        columns={columns}
        keyField="id"
        onRowClick={onSelectVersion}
        className={styles.versionsTable}
      />
    </div>
  );
}

export default VersionsBlock;
