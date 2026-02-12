/**
 * LimitVersionContent - Entity-specific content for limit version preview
 * 
 * Displays limits configuration in a grid layout
 */
import React from 'react';
import styles from './LimitVersionContent.module.css';

export interface LimitVersionContentProps {
  version: {
    version: number;
    max_steps?: number;
    max_tool_calls?: number;
    max_wall_time_ms?: number;
    tool_timeout_ms?: number;
    max_retries?: number;
    extra_config?: Record<string, any>;
    notes?: string;
    [key: string]: any;
  };
}

export function LimitVersionContent({ version }: LimitVersionContentProps) {
  return (
    <div className={styles.limitsGrid}>
      <div className={styles.limitItem}>
        <span className={styles.label}>Шаги:</span>
        <span className={styles.value}>{version.max_steps ?? '∞'}</span>
      </div>
      <div className={styles.limitItem}>
        <span className={styles.label}>Вызовы:</span>
        <span className={styles.value}>{version.max_tool_calls ?? '∞'}</span>
      </div>
      <div className={styles.limitItem}>
        <span className={styles.label}>Повторы:</span>
        <span className={styles.value}>{version.max_retries ?? '∞'}</span>
      </div>
      <div className={styles.limitItem}>
        <span className={styles.label}>Таймаут:</span>
        <span className={styles.value}>
          {version.max_wall_time_ms ? `${version.max_wall_time_ms / 1000}s` : '∞'}
        </span>
      </div>
      <div className={styles.limitItem}>
        <span className={styles.label}>Таймаут инструмента:</span>
        <span className={styles.value}>
          {version.tool_timeout_ms ? `${version.tool_timeout_ms / 1000}s` : '∞'}
        </span>
      </div>
      
      {version.notes && (
        <div className={styles.notesSection}>
          <span className={styles.notesLabel}>Заметки:</span>
          <div className={styles.notesText}>
            {version.notes.length > 100
              ? `${version.notes.substring(0, 100)}...`
              : version.notes}
          </div>
        </div>
      )}
    </div>
  );
}

export default LimitVersionContent;
