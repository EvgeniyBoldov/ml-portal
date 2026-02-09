/**
 * ShortVersionCard - Compact version display for EntityTabsPage
 * 
 * Used inside ShortEntityBlock to show version content without extra wrapper
 * Each entity type has its own short version card
 */
import React from 'react';
import styles from './VersionCard.module.css';

export interface ShortVersionCardProps {
  entityType: 'prompt' | 'baseline' | 'policy' | 'agent' | 'limit' | 'tool';
  version: {
    version: number;
    status: string;
    created_at: string;
    updated_at?: string;
    notes?: string;
    template?: string; // prompt/baseline
    limits?: any; // policy
    [key: string]: any;
  } | null;
}

export function ShortVersionCard({ entityType, version }: ShortVersionCardProps) {
  if (!version) {
    return (
      <div className={styles.emptyState}>
        <p className={styles.emptyText}>Нет активной версии</p>
      </div>
    );
  }

  switch (entityType) {
    case 'prompt':
      return <ShortPromptVersionCard version={version} />;
    case 'baseline':
      return <ShortBaselineVersionCard version={version} />;
    case 'policy':
      return <ShortPolicyVersionCard version={version} />;
    default:
      return <div>Неизвестный тип сущности</div>;
  }
}

// Prompt version card - shows template in textarea
function ShortPromptVersionCard({ version }: { version: any }) {
  return (
    <div className={styles.shortVersionCard}>
      {version.template ? (
        <textarea
          className={styles.templateInput}
          value={version.template}
          readOnly
          rows={6}
        />
      ) : (
        <div className={styles.emptyText}>Нет шаблона</div>
      )}
    </div>
  );
}

// Baseline version card - similar to prompt
function ShortBaselineVersionCard({ version }: { version: any }) {
  return (
    <div className={styles.shortVersionCard}>
      {version.template ? (
        <textarea
          className={styles.templateInput}
          value={version.template}
          readOnly
          rows={6}
        />
      ) : (
        <div className={styles.emptyText}>Нет бейслайна</div>
      )}
    </div>
  );
}

// Policy version card - shows limits, timeouts, budget in tables
function ShortPolicyVersionCard({ version }: { version: any }) {
  const renderTable = (title: string, data: Record<string, any>) => {
    if (!data || Object.keys(data).length === 0) return null;
    
    return (
      <div key={title} style={{ marginBottom: '1rem' }}>
        <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: '0.5rem', textTransform: 'uppercase' }}>
          {title}
        </div>
        <table className={styles.table}>
          <tbody>
            {Object.entries(data).map(([key, value]) => (
              <tr key={key} className={styles.tableRow}>
                <td className={styles.tableKey}>{key}</td>
                <td className={styles.tableValue}>
                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  const limits = {
    'Макс. шагов': version.max_steps,
    'Макс. вызовов': version.max_tool_calls,
    'Макс. повторов': version.max_retries,
  };

  const timeouts = {
    'Общий таймаут (мс)': version.max_wall_time_ms,
    'Таймаут инструмента (мс)': version.tool_timeout_ms,
  };

  const budget = {
    'Лимит токенов': version.budget_tokens,
    'Лимит стоимости (центы)': version.budget_cost_cents,
  };

  const hasData = Object.values(limits).some(v => v !== undefined) ||
                  Object.values(timeouts).some(v => v !== undefined) ||
                  Object.values(budget).some(v => v !== undefined) ||
                  version.notes;

  if (!hasData) {
    return <div className={styles.emptyText}>Нет параметров</div>;
  }

  return (
    <div className={styles.shortVersionCard}>
      {renderTable('Лимиты', Object.fromEntries(Object.entries(limits).filter(([, v]) => v !== undefined)))}
      {renderTable('Таймауты', Object.fromEntries(Object.entries(timeouts).filter(([, v]) => v !== undefined)))}
      {renderTable('Бюджет', Object.fromEntries(Object.entries(budget).filter(([, v]) => v !== undefined)))}
      {version.notes && (
        <div style={{ marginTop: '1rem' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: '0.5rem', textTransform: 'uppercase' }}>
            Заметки
          </div>
          <div className={styles.notesText}>{version.notes}</div>
        </div>
      )}
    </div>
  );
}

export default ShortVersionCard;
