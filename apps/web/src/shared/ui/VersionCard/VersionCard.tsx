/**
 * VersionCard - Universal compact version display component
 * 
 * Adapts to different entity types:
 * - Prompt/Baseline: Shows template preview
 * - Tool: Shows configuration
 */
import React from 'react';
import { ContentBlock } from '../ContentBlock';
import { MetaRow } from '../MetaRow';
import Badge from '../Badge';
import Button from '../Button';
import { useStatusConfig } from '@/shared/hooks/useStatusConfig';
import styles from './VersionCard.module.css';

export type VersionCardEntityType = 'prompt' | 'baseline' | 'tool';

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
  /** Render without ContentBlock wrapper */
  noWrapper?: boolean;
}

export function VersionCard({
  entityType,
  version,
  onCreateVersion,
  children,
  className = '',
  noWrapper = false,
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

  const cardContent = (
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
  );

  if (noWrapper) {
    return cardContent;
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
      {cardContent}
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
      noWrapper={true}
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


export default VersionCard;
