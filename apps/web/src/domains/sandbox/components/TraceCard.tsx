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

const formatTitle = (entity: TraceEntity): string => {
  const { kind, data, title } = entity;

  switch (kind) {
    case 'run':
      if (data.kind === 'run') return data.userRequest?.slice(0, 60) ?? title;
      return title;
    case 'orchestrator':
      if (data.kind === 'orchestrator') return data.slug ?? title;
      return title;
    case 'planner':
      if (data.kind === 'planner') {
        const kindLabel = data.stepKind ?? 'planner';
        const rationale = data.rationale?.slice(0, 40);
        return rationale ? `${kindLabel}: ${rationale}` : kindLabel;
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

const KIND_BADGES: Record<string, { label: string; tone: 'neutral' | 'success' | 'warn' | 'danger' | 'info' }> = {
  run: { label: 'Run', tone: 'neutral' },
  orchestrator: { label: 'Orc', tone: 'info' },
  planner: { label: 'Plan', tone: 'info' },
  agent: { label: 'Agent', tone: 'success' },
  llm: { label: 'LLM', tone: 'info' },
  tool: { label: 'Tool', tone: 'neutral' },
  decision: { label: 'Dec', tone: 'info' },
  error: { label: 'Err', tone: 'danger' },
  unknown: { label: 'New', tone: 'warn' },
};

// Краткий сквозной вид по логу: приоритет на агент/планер/тул
const BUDGET_KINDS: Record<string, Array<'steps' | 'tools' | 'retries' | 'tokens' | 'wallTimeMs'>> = {
  run: ['steps', 'tools'],
  orchestrator: ['steps', 'wallTimeMs'],
  agent: ['steps', 'tools', 'tokens', 'wallTimeMs'],
  llm: ['tokens', 'wallTimeMs'],
  tool: ['tools', 'retries', 'wallTimeMs'],
  planner: ['steps', 'wallTimeMs'],
  decision: ['steps'],
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

export function TraceCard({
  entity,
  isExpanded,
  onToggle,
  onSelect,
  isSelected,
  hasChildren,
}: TraceCardProps): React.ReactElement {
  const { kind, status, durationMs, budgetSnapshot, budgetDelta, children } = entity;

  const title = formatTitle(entity);
  const badge = KIND_BADGES[kind] ?? { label: kind, tone: 'neutral' as const };
  const effectiveBadge =
    kind === 'orchestrator' && entity.data.kind === 'orchestrator'
      ? {
          ...badge,
          label: /synth/i.test(entity.data.slug ?? '') || entity.data.role === 'synthesizer' ? 'SYNT' : 'ORC',
        }
      : badge;
  const budgetKinds = BUDGET_KINDS[kind] ?? [];
  const showTotals = kind === 'run' || kind === 'agent';
  const pillsSnapshot = showTotals ? budgetSnapshot : undefined;
  const pillsDelta = showTotals ? undefined : budgetDelta;
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
        styles[kind],
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

        <Badge tone={effectiveBadge.tone} size="small" className={styles.kindBadge}>
          {effectiveBadge.label}
        </Badge>

        <span className={[styles.statusIcon, styles[status]].join(' ')}>
          {statusIcon}
        </span>

        <span className={styles.title} title={title}>
          {title}
        </span>

        {collapsedSummary && <span className={styles.collapsedSummary}>{collapsedSummary}</span>}

        {durationMs !== undefined && (
          <span className={styles.duration}>
            {(durationMs / 1000).toFixed(1)}s
          </span>
        )}

        {budgetKinds.length > 0 && (
          <BudgetPills
            snapshot={pillsSnapshot}
            delta={pillsDelta}
            kinds={budgetKinds}
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
