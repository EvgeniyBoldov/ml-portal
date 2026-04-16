import React from 'react';
import { Badge, type DataTableColumn } from '@/shared/ui';
import {
  RBAC_EFFECT_LABELS,
  RBAC_EFFECT_TONES,
  RBAC_LEVEL_LABELS,
  RBAC_LEVEL_TONES,
  RBAC_RESOURCE_TYPE_LABELS,
} from './rbacLabels';
import type { Agent } from '@/shared/api/agents';
import type { ToolInstance } from '@/shared/api/toolInstances';
import type { EnrichedRule, ResourceType, RbacEffect } from '@/shared/api/rbac';

interface BuildRbacRuleColumnsArgs {
  showOwner?: boolean;
  agentById?: Map<string, Agent>;
  instanceById?: Map<string, ToolInstance>;
}

export function resolveRbacOwnerLabel(row: EnrichedRule): string {
  return row.owner.name?.trim() || RBAC_LEVEL_LABELS[row.owner.level] || '—';
}

export function resolveRbacResourceLabel(
  row: EnrichedRule,
  agentById?: Map<string, Agent>,
  instanceById?: Map<string, ToolInstance>,
): string {
  if (row.resource.type === 'agent') {
    const agent = agentById?.get(row.resource.id);
    if (agent) {
      return agent.name?.trim() || agent.slug?.trim() || row.resource.name?.trim() || row.resource.slug?.trim() || RBAC_RESOURCE_TYPE_LABELS.agent;
    }
  }

  if (row.resource.type === 'instance') {
    const instance = instanceById?.get(row.resource.id);
    if (instance) {
      return instance.name?.trim() || instance.slug?.trim() || row.resource.name?.trim() || row.resource.slug?.trim() || RBAC_RESOURCE_TYPE_LABELS.instance;
    }
  }

  return row.resource.name?.trim() || row.resource.slug?.trim() || RBAC_RESOURCE_TYPE_LABELS[row.resource.type as ResourceType] || '—';
}

export function resolveRbacSearchText(
  row: EnrichedRule,
  agentById?: Map<string, Agent>,
  instanceById?: Map<string, ToolInstance>,
): string {
  return [
    resolveRbacOwnerLabel(row),
    row.owner.level,
    resolveRbacResourceLabel(row, agentById, instanceById),
    row.resource.type,
    row.effect,
    row.created_by_name || '',
    new Date(row.created_at).toLocaleString('ru-RU'),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

function effectBadge(effect: RbacEffect) {
  return <Badge tone={RBAC_EFFECT_TONES[effect]}>{RBAC_EFFECT_LABELS[effect]}</Badge>;
}

export function buildRbacRuleColumns({
  showOwner = true,
  agentById,
  instanceById,
}: BuildRbacRuleColumnsArgs): DataTableColumn<EnrichedRule>[] {
  const columns: DataTableColumn<EnrichedRule>[] = [];

  if (showOwner) {
    columns.push({
      key: 'target',
      label: 'Владелец',
      width: 240,
      sortable: true,
      sortValue: (row) => row.owner.level,
      filter: {
        kind: 'select',
        placeholder: 'Все уровни',
        options: [
          { value: 'platform', label: 'Платформа' },
          { value: 'tenant', label: 'Тенант' },
          { value: 'user', label: 'Пользователь' },
        ],
        getValue: (row) => row.owner.level,
      },
      render: (row) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontWeight: 500 }}>{resolveRbacOwnerLabel(row)}</span>
          <Badge tone={RBAC_LEVEL_TONES[row.owner.level]}>{RBAC_LEVEL_LABELS[row.owner.level]}</Badge>
        </div>
      ),
    });
  }

  columns.push(
    {
      key: 'resource',
      label: 'Ресурс',
      width: 240,
      sortable: true,
      sortValue: (row) => resolveRbacResourceLabel(row, agentById, instanceById),
      filter: {
        kind: 'select',
        placeholder: 'Все ресурсы',
        options: [
          { value: 'agent', label: 'Агенты' },
          { value: 'tool', label: 'Инструменты' },
          { value: 'instance', label: 'Коннекторы' },
        ],
        getValue: (row) => row.resource.type,
      },
      render: (row) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontWeight: 500 }}>{resolveRbacResourceLabel(row, agentById, instanceById)}</span>
          <Badge tone="neutral">{RBAC_RESOURCE_TYPE_LABELS[row.resource.type as ResourceType]}</Badge>
        </div>
      ),
    },
    {
      key: 'effect',
      label: 'Эффект',
      width: 120,
      sortable: true,
      sortValue: (row) => row.effect,
      filter: {
        kind: 'select',
        placeholder: 'Все эффекты',
        options: [
          { value: 'allow', label: 'Разрешён' },
          { value: 'deny', label: 'Запрещён' },
        ],
        getValue: (row) => row.effect,
      },
      render: (row) => effectBadge(row.effect),
    },
    {
      key: 'created_at',
      label: 'Создано',
      width: 170,
      sortable: true,
      sortValue: (row) => row.created_at,
      filter: {
        kind: 'date-range',
        fromPlaceholder: 'От',
        toPlaceholder: 'До',
        getValue: (row) => row.created_at,
      },
      render: (row) => (
        <span style={{ color: 'var(--text-secondary)' }}>
          {new Date(row.created_at).toLocaleString('ru-RU', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      ),
    },
  );

  return columns;
}
