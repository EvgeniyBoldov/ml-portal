/**
 * VersionCard - Universal compact version display component
 * 
 * Adapts to different entity types:
 * - Prompt/Baseline: Shows template preview
 * - Policy: Shows limits table
 * - Tool: Shows configuration
 */
import React from 'react';
import { ContentBlock } from '../ContentBlock';
import { MetaRow } from '../MetaRow';
import Badge from '../Badge';
import Button from '../Button';
import { useStatusConfig } from '@/shared/hooks/useStatusConfig';
import styles from './VersionCard.module.css';

export type VersionCardEntityType = 'prompt' | 'baseline' | 'policy' | 'tool';

export interface VersionCardProps {
  entityType: VersionCardEntityType;
  version: {
    version: number;
    status: string;
    created_at: string;
    updated_at?: string;
    notes?: string;
    [key: string]: any; // Allow additional fields
  } | null;
  onCreateVersion?: () => void;
  children?: React.ReactNode;
  className?: string;
}

export function VersionCard({
  entityType,
  version,
  onCreateVersion,
  children,
  className = '',
}: VersionCardProps) {
  const statusConfig = useStatusConfig(entityType);

  if (!version) {
    return (
      <ContentBlock
        width="full"
        title="Версия"
        className={className}
      >
        <div className={styles.emptyState}>
          <p className={styles.emptyText}>Нет активной версии</p>
          {onCreateVersion && (
            <Button variant="primary" onClick={onCreateVersion}>
              Создать версию
            </Button>
          )}
        </div>
      </ContentBlock>
    );
  }

  return (
    <ContentBlock
      width="full"
      title={`Версия v${version.version}`}
      headerActions={
        <Badge tone={statusConfig.tones[version.status]}>
          {statusConfig.labels[version.status]}
        </Badge>
      }
      className={className}
    >
      <div className={styles.versionCard}>
        {/* Metadata */}
        <div className={styles.metadata}>
          <MetaRow
            label="Создана"
            value={new Date(version.created_at).toLocaleDateString('ru-RU')}
          />
          {version.updated_at && (
            <MetaRow
              label="Обновлена"
              value={new Date(version.updated_at).toLocaleDateString('ru-RU')}
            />
          )}
          {version.notes && (
            <MetaRow label="Заметки" value={version.notes} />
          )}
        </div>

        {/* Custom content */}
        {children && (
          <div className={styles.content}>
            {children}
          </div>
        )}
      </div>
    </ContentBlock>
  );
}

// Specialized version cards for different entity types

export interface PromptVersionCardProps {
  version: {
    version: number;
    status: string;
    created_at: string;
    updated_at?: string;
    template: string;
  } | null;
  onCreateVersion?: () => void;
}

export function PromptVersionCard({ version, onCreateVersion }: PromptVersionCardProps) {
  return (
    <VersionCard
      entityType="prompt"
      version={version}
      onCreateVersion={onCreateVersion}
    >
      {version?.template && (
        <div className={styles.templatePreview}>
          <div className={styles.templateLabel}>Шаблон:</div>
          <pre className={styles.templateContent}>
            {version.template.length > 200
              ? `${version.template.substring(0, 200)}...`
              : version.template}
          </pre>
        </div>
      )}
    </VersionCard>
  );
}

export interface PolicyVersionCardProps {
  version: {
    version: number;
    status: string;
    created_at: string;
    updated_at?: string;
    max_steps?: number;
    max_tool_calls?: number;
    max_wall_time_ms?: number;
  } | null;
  onCreateVersion?: () => void;
}

export function PolicyVersionCard({ version, onCreateVersion }: PolicyVersionCardProps) {
  return (
    <VersionCard
      entityType="policy"
      version={version}
      onCreateVersion={onCreateVersion}
    >
      {version && (
        <div className={styles.limitsTable}>
          <div className={styles.limitsLabel}>Лимиты:</div>
          <div className={styles.limitsGrid}>
            <MetaRow
              label="Макс. шагов"
              value={version.max_steps ?? '∞'}
            />
            <MetaRow
              label="Макс. вызовов"
              value={version.max_tool_calls ?? '∞'}
            />
            {version.max_wall_time_ms && (
              <MetaRow
                label="Таймаут"
                value={`${version.max_wall_time_ms / 1000}s`}
              />
            )}
          </div>
        </div>
      )}
    </VersionCard>
  );
}

export default VersionCard;
