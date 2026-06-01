/**
 * TraceCard — отображение одной TraceEntity в иерархическом трейсе
 */

import * as React from 'react';
import type { MouseEvent } from 'react';
import Badge from '@/shared/ui/Badge';
import { Icon } from '@/shared/ui/Icon';
import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import { BudgetPills } from '@/domains/runtimeTrace/budget';
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
  badgeLabel: string;
  badgeTone: 'neutral' | 'success' | 'warn' | 'danger' | 'info';
  className: string;
}

const formatTitle = (entity: TraceEntity): string => {
  const { kind, data, title } = entity;

  switch (kind) {
    case 'run':
      if (data.kind === 'run') return data.userRequest?.slice(0, 60) ?? title;
      return title;
    case 'orchestrator':
      if (data.kind === 'orchestrator') {
        if (title && title !== data.slug) return title;
        if (data.role === 'synthesizer') return 'Синтезер';
        if (data.role === 'planner') return 'Подготовка ответа';
        if (data.role === 'memory') return 'Мемори';
        return data.slug ?? title;
      }
      return title;
    case 'planner':
      if (data.kind === 'planner') {
        const rationale = data.rationale?.trim();
        if (rationale) return rationale.slice(0, 72);
        if (data.stepKind === 'call_agent') {
          return data.decision?.chosenAgentSlug
            ? `Агент: ${data.decision.chosenAgentSlug}`
            : 'Вызов агента';
        }
        if (data.stepKind === 'final' || data.stepKind === 'direct_answer') return 'Ответ пользователю';
        return 'Шаг планера';
      }
      return title;
    case 'agent':
      if (data.kind === 'agent') {
        const version = data.versionLabel ? ` · ${data.versionLabel}` : '';
        const overrides = data.hasOverrides ? ' (с оверайдами)' : '';
        return `${data.slug}${version}${overrides}`;
      }
      return title;
    case 'llm':
      if (data.kind === 'llm') {
        const firstMsg = data.prompt?.messages?.[0];
        if (firstMsg && typeof firstMsg.content === 'string') return firstMsg.content.slice(0, 50);
        return 'LLM';
      }
      return title;
    case 'tool':
      if (data.kind === 'tool') return data.toolSlug;
      return title;
    case 'error':
      if (data.kind === 'error') {
        return data.code ? `${data.code}: ${data.userMessage?.slice(0, 40)}` : (data.userMessage?.slice(0, 50) ?? title);
      }
      return title;
    case 'unknown':
      if (data.kind === 'unknown') return `${data.rawType} 🆕`;
      return title;
    default:
      return title;
  }
};

const formatPlannerStepKind = (stepKind?: string): string => {
  const normalized = String(stepKind ?? '').toLowerCase();
  if (normalized === 'call_agent') return 'Вызвать агента';
  if (normalized === 'final') return 'Финальный ответ';
  if (normalized === 'ask_user') return 'Уточнение';
  if (normalized === 'direct_answer') return 'Прямой ответ';
  if (normalized === 'abort') return 'Прервать';
  if (normalized === 'iteration') return 'Итерация планера';
  return stepKind ?? 'planner';
};

const resolveToneMeta = (entity: TraceEntity): ToneMeta => {
  if (entity.kind === 'orchestrator' && entity.data.kind === 'orchestrator') {
    if (entity.data.role === 'synthesizer') {
      return { badgeLabel: 'SYNT', badgeTone: 'info', className: styles.synthesis };
    }
    if (entity.data.role === 'memory') {
      return { badgeLabel: 'MEM', badgeTone: 'warn', className: styles.fact };
    }
    if (entity.data.role === 'fact_extractor') {
      return { badgeLabel: 'FACT', badgeTone: 'warn', className: styles.fact };
    }
    return { badgeLabel: 'PLAN', badgeTone: 'info', className: styles.planner };
  }
  if (entity.kind === 'agent' && entity.data.kind === 'agent') {
    const slug = String(entity.data.slug ?? '').toLowerCase();
    if (slug === 'facts' || slug === 'fact_extractor') {
      return { badgeLabel: 'FACT', badgeTone: 'warn', className: styles.fact };
    }
    if (slug === 'conversation' || slug === 'summary_compactor') {
      return { badgeLabel: 'SUM', badgeTone: 'warn', className: styles.synthesis };
    }
  }
  if (entity.kind === 'planner') {
    return { badgeLabel: 'PLAN', badgeTone: 'info', className: styles.planner };
  }
  if (entity.kind === 'llm') return { badgeLabel: 'LLM', badgeTone: 'warn', className: styles.llm };
  if (entity.kind === 'agent') return { badgeLabel: 'AGENT', badgeTone: 'success', className: styles.agent };
  if (entity.kind === 'tool') return { badgeLabel: 'TOOL', badgeTone: 'neutral', className: styles.tool };
  if (entity.kind === 'run') return { badgeLabel: 'RUN', badgeTone: 'neutral', className: styles.run };
  if (entity.kind === 'error') return { badgeLabel: 'ERR', badgeTone: 'danger', className: styles.error };
  return { badgeLabel: 'NEW', badgeTone: 'warn', className: styles.unknown };
};

// Краткий сквозной вид по логу: приоритет на агент/планер/тул
const BUDGET_KINDS: Record<string, Array<'planner_steps' | 'agent_steps' | 'tool_calls' | 'tokens_total' | 'retries' | 'wall_time_ms'>> = {
  run: ['planner_steps', 'tool_calls'],
  orchestrator: ['planner_steps', 'tokens_total', 'wall_time_ms'],
  agent: ['agent_steps', 'tokens_total', 'wall_time_ms'],
  llm: ['tokens_total'],
  tool: ['tool_calls', 'retries', 'wall_time_ms'],
  planner: ['planner_steps', 'wall_time_ms'],
  decision: ['planner_steps'],
  error: [],
  unknown: [],
};

const STATUS_ICONS: Record<string, string> = {
  ok: '✓',
  warn: '◆',
  error: '✕',
  info: '○',
  pending: '◌',
};

function StepMeta({
  entity,
  durationMs,
  collapsedSummary,
}: {
  entity: TraceEntity;
  durationMs?: number;
  collapsedSummary: string | null;
}): React.ReactElement {
  const plannerAction =
    entity.kind === 'planner' && entity.data.kind === 'planner'
      ? (
        entity.data.stepKind === 'call_agent' && entity.data.decision?.chosenAgentSlug
          ? `${formatPlannerStepKind(entity.data.stepKind)}: ${entity.data.decision.chosenAgentSlug}`
          : formatPlannerStepKind(entity.data.stepKind)
      )
      : null;

  return (
    <>
      {plannerAction && <span className={styles.actionType}>{plannerAction}</span>}
      {collapsedSummary && <span className={styles.collapsedSummary}>{collapsedSummary}</span>}
      {durationMs !== undefined && (
        <span className={styles.duration}>
          {(durationMs / 1000).toFixed(1)}s
        </span>
      )}
    </>
  );
}

export function TraceCard({
  entity,
  isExpanded,
  onToggle,
  onSelect,
  isSelected,
  hasChildren,
}: TraceCardProps): React.ReactElement {
  const { kind, status, durationMs, children } = entity;

  const title = formatTitle(entity);
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
  const showAggregated = kind === 'run' || kind === 'orchestrator' || kind === 'agent';
  const pillsUsed = showAggregated ? entity.budget?.aggregated : entity.budget?.own;
  const pillsLimits = entity.budget?.limits ?? null;
  const statusIcon = STATUS_ICONS[status] ?? '○';

  let collapsedSummary: string | null = null;
  if (!isExpanded && kind === 'agent' && children.length > 0) {
    const llmCount = children.filter((c) => c.kind === 'llm').length;
    const toolCount = children.filter((c) => c.kind === 'tool').length;
    const parts: string[] = [];
    if (llmCount > 0) parts.push(`${llmCount} LLM`);
    if (toolCount > 0) parts.push(`${toolCount} tool`);
    if (durationMs !== undefined) parts.push(`${(durationMs / 1000).toFixed(1)}s`);
    if (parts.length > 0) collapsedSummary = parts.join(' · ');
  }

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

        <Badge tone={toneMeta.badgeTone} size="small" className={styles.kindBadge}>
          {toneMeta.badgeLabel}
        </Badge>

        <span className={[styles.statusIcon, styles[status]].join(' ')}>
          {statusIcon}
        </span>

        <span className={styles.title} title={title}>
          {title}
        </span>

        <StepMeta entity={entity} durationMs={durationMs} collapsedSummary={collapsedSummary} />

        {budgetKinds.length > 0 && (
          <BudgetPills
            used={pillsUsed}
            limits={pillsLimits}
            metrics={budgetKinds}
            className={styles.budgetPills}
          />
        )}

        {isUnknown && (
          <span className={styles.unknownHint} title="Новый/неклассифицированный шаг — добавь в normalize.ts">
            🆕
          </span>
        )}
      </div>
    </div>
  );
}
