/**
 * TraceCard — отображение одной TraceEntity в иерархическом трейсе
 */

import * as React from 'react';
import type { MouseEvent } from 'react';
import { Icon } from '@/shared/ui/Icon';
import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import { BudgetPills } from '@/domains/runtimeTrace/budget';
import {
  getTraceEntityKindLabel,
  getTraceEntityTitle,
  isMemorySnapshotAgent,
} from '@/domains/runtimeTrace/tracePresentation';
import styles from './TraceCard.module.css';

interface TraceCardProps {
  entity: TraceEntity;
  isExpanded: boolean;
  onToggle: () => void;
  onSelect: () => void;
  isSelected: boolean;
  hasChildren: boolean;
}

interface ToneMeta {
  className: string;
}

function formatDuration(durationMs?: number): string {
  if (durationMs === undefined || durationMs === null) return '—';
  return `${(durationMs / 1000).toFixed(1).replace('.', ',')} s`;
}

const resolveToneMeta = (entity: TraceEntity): ToneMeta => {
  if (entity.kind === 'orchestrator' && entity.data.kind === 'orchestrator') {
    if (entity.data.role === 'synthesizer') {
      return { className: styles.synthesis };
    }
    if (entity.data.role === 'memory') {
      return { className: styles.fact };
    }
    if (entity.data.role === 'fact_extractor') {
      return { className: styles.fact };
    }
    return { className: styles.planner };
  }
  if (entity.kind === 'phase' && entity.data.kind === 'phase') {
    if (entity.data.phaseRole === 'active') {
      return { className: styles.planner };
    }
    return { className: styles.fact };
  }
  if (isMemorySnapshotAgent(entity)) {
    return { className: styles.orchestrator };
  }
  if (entity.kind === 'planner') return { className: styles.planner };
  if (entity.kind === 'llm') return { className: styles.llm };
  if (entity.kind === 'agent') return { className: styles.agent };
  if (entity.kind === 'tool') return { className: styles.tool };
  if (entity.kind === 'run') return { className: styles.run };
  if (entity.kind === 'error') return { className: styles.error };
  return { className: styles.unknown };
};

// Краткий сквозной вид по логу: приоритет на агент/планер/тул
const BUDGET_KINDS: Record<string, Array<'planner_steps' | 'agent_steps' | 'tool_calls' | 'tokens_total' | 'retries' | 'wall_time_ms'>> = {
  run: ['planner_steps', 'tool_calls'],
  phase: ['planner_steps', 'agent_steps', 'tool_calls', 'tokens_total', 'wall_time_ms'],
  orchestrator: ['planner_steps', 'tokens_total', 'wall_time_ms'],
  agent: ['agent_steps', 'tokens_total', 'wall_time_ms'],
  llm: ['tokens_total'],
  tool: ['tool_calls', 'retries', 'wall_time_ms'],
  planner: ['planner_steps', 'wall_time_ms'],
  decision: ['planner_steps'],
  error: [],
  unknown: [],
};

function statusLabel(status: TraceEntity['status']): string {
  if (status === 'ok') return 'Успешно';
  if (status === 'warn') return 'Предупреждение';
  if (status === 'error') return 'Ошибка';
  if (status === 'pending') return 'В процессе';
  return 'Инфо';
}

export function TraceCard({
  entity,
  isExpanded,
  onToggle,
  onSelect,
  isSelected,
  hasChildren,
}: TraceCardProps): React.ReactElement {
  const { kind, status, durationMs } = entity;

  const title = getTraceEntityTitle(entity);
  const toneMeta = resolveToneMeta(entity);
  const budgetKinds = (() => {
    if (entity.kind === 'agent' && entity.data.kind === 'agent') {
      const slug = String(entity.data.slug ?? '').toLowerCase();
      if (slug === 'facts' || slug === 'fact_extractor' || slug === 'conversation' || slug === 'summary_compactor') {
        return ['tokens_total', 'wall_time_ms'] as Array<'planner_steps' | 'agent_steps' | 'tool_calls' | 'tokens_total' | 'retries' | 'wall_time_ms'>;
      }
    }
    return BUDGET_KINDS[kind] ?? [];
  })();
  const showAggregated = kind === 'run' || kind === 'orchestrator' || kind === 'agent' || kind === 'phase';
  const pillsUsed = showAggregated ? entity.budget?.aggregated : entity.budget?.own;
  const pillsLimits = entity.budget?.limits ?? null;
  const isUnknown = kind === 'unknown';

  return (
    <div
      className={[
        styles.card,
        toneMeta.className,
        isSelected && styles.selected,
        isUnknown && styles.unknown,
        status === 'error' && styles.error,
      ].filter(Boolean).join(' ')}
      style={{ marginLeft: `${entity.depth * 16}px` }}
    >
      <div className={styles.header} onClick={onSelect}>
        {hasChildren && (
          <button
            className={styles.expandBtn}
            onClick={(e: MouseEvent<HTMLButtonElement>) => {
              e.stopPropagation();
              onToggle();
            }}
            title={isExpanded ? 'Свернуть' : 'Развернуть'}
          >
            {isExpanded ? <Icon name="chevron-down" size={16} /> : <Icon name="chevron-right" size={16} />}
          </button>
        )}
        {!hasChildren && <span className={styles.expandPlaceholder} />}

        <span className={styles.kindChip}>{getTraceEntityKindLabel(entity)}</span>

        <span className={styles.title} title={title}>
          {title}
        </span>

        <span className={styles.rightMeta}>
          <span className={styles.metaBudget}>
            {budgetKinds.length > 0 ? (
              <BudgetPills
                used={pillsUsed}
                limits={pillsLimits}
                metrics={budgetKinds}
                className={styles.budgetPills}
              />
            ) : null}
          </span>
          <span className={styles.metaDuration}>{formatDuration(durationMs)}</span>
          <span className={styles.statusCol}>
            <span className={`${styles.statusDot} ${styles[`status_${status}`]}`} title={statusLabel(status)} />
          </span>
        </span>
      </div>
    </div>
  );
}
