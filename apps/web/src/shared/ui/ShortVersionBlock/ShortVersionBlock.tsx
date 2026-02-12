/**
 * ShortVersionBlock - Universal block for displaying version preview
 * 
 * Provides meta information (version number, dates) by default
 * and accepts children for entity-specific content
 */
import React from 'react';
import { ContentBlock } from '../ContentBlock';
import { MetaRow } from '../MetaRow';
import Badge from '../Badge';
import { useStatusConfig } from '@/shared/hooks/useStatusConfig';
import styles from './ShortVersionBlock.module.css';

export interface ShortVersionBlockProps {
  title: string;
  subtitle?: string;
  entityType?: 'prompt' | 'baseline' | 'policy' | 'agent' | 'limit' | 'tool';
  version: {
    version: number;
    created_at: string;
    activated_at?: string;
    status?: string;
    [key: string]: any;
  };
  children?: React.ReactNode;
  className?: string;
}

export function ShortVersionBlock({
  title,
  subtitle,
  entityType = 'policy', // default по умолчанию
  version,
  children,
  className,
}: ShortVersionBlockProps) {
  const statusConfig = useStatusConfig(entityType);

  // Header actions with status badge
  const headerActions = version.status ? (
    <Badge tone={statusConfig.tones[version.status] || 'neutral'} size="small">
      {statusConfig.labels[version.status] || version.status}
    </Badge>
  ) : undefined;

  return (
    <ContentBlock
      title={title}
      subtitle={subtitle}
      headerActions={headerActions}
      className={className}
    >
      {/* Meta information */}
      <div className={styles.metaInfo}>
        <MetaRow 
          label="Версия" 
          value={`v${version.version}`} 
        />
        <MetaRow 
          label="Создана" 
          value={new Date(version.created_at).toLocaleDateString('ru-RU')} 
        />
        {version.activated_at && (
          <MetaRow 
            label="Активирована" 
            value={new Date(version.activated_at).toLocaleDateString('ru-RU')} 
          />
        )}
      </div>

      {/* Entity-specific content */}
      {children && (
        <div className={styles.content}>
          {children}
        </div>
      )}
    </ContentBlock>
  );
}

export default ShortVersionBlock;
