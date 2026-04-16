/**
 * EntityField — отображает название сущности по UUID с тултипом.
 *
 * Режимы:
 *   - mode="full" (default) — показывает имя сущности, тултип с деталями
 *   - mode="short" — показывает короткий UUID (8 символов), тултип с именем и деталями
 *
 * Использование:
 *   <EntityField id={rule.resource_id} entityType="agent" />
 *   <EntityField id={rule.owner_user_id} name={user.login} type="Пользователь" />
 */
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { agentsApi, type AgentDetail } from '@/shared/api/agents';
import { qk } from '@/shared/api/keys';
import { Tooltip } from '../Tooltip';
import styles from './EntityField.module.css';

export interface EntityFieldProps {
  /** UUID сущности */
  id: string | null | undefined;
  /** Тип сущности для автоматической загрузки */
  entityType?: 'agent';
  /** Режим отображения: full — имя, short — короткий UUID */
  mode?: 'full' | 'short';
  /** Человекочитаемое название (если уже известно) */
  name?: string | null;
  /** Тип сущности — отображается в тултипе */
  type?: string;
  /** Дополнительная информация в тултипе (slug, email и т.д.) */
  meta?: string | null;
  /** Заглушка когда id отсутствует */
  fallback?: string;
  /** Позиция тултипа */
  tooltipPosition?: 'top' | 'bottom' | 'left' | 'right';
}

function AgentTooltipContent({ agent, id }: { agent: AgentDetail; id: string }) {
  return (
    <div className={styles['tooltip-content']}>
      <div className={styles['tooltip-type']}>Агент</div>
      <div className={styles['tooltip-name']}>{agent.name}</div>
      <code className={styles['tooltip-id']}>{id}</code>
      <div className={styles['tooltip-meta']}>Slug: {agent.slug}</div>
      {agent.description && (
        <div className={styles['tooltip-description']}>{agent.description}</div>
      )}
      {agent.current_version_id && (
        <div className={styles['tooltip-meta']}>
          Текущая версия: {shortUuid(agent.current_version_id)}
        </div>
      )}
    </div>
  );
}

function shortUuid(id: string): string {
  return id.slice(0, 8) + '…';
}

export function EntityField({
  id,
  entityType,
  mode = 'full',
  name,
  type,
  meta,
  fallback = '—',
  tooltipPosition = 'top',
}: EntityFieldProps) {
  const { data: agent, isLoading: agentLoading } = useQuery({
    queryKey: qk.agents.detail(id!),
    queryFn: () => agentsApi.get(id!),
    enabled: !!id && entityType === 'agent',
    staleTime: 60_000,
  });

  if (!id) {
    return <span className={styles.fallback}>{fallback}</span>;
  }

  const isLoading = entityType === 'agent' && agentLoading;

  if (isLoading) {
    return <span className={styles.loading}>{shortUuid(id)}</span>;
  }

  // ─── Agent ───
  if (entityType === 'agent' && agent) {
    const tooltipContent = <AgentTooltipContent agent={agent} id={id} />;
    return (
      <Tooltip content={tooltipContent} position={tooltipPosition}>
        <span className={styles.name}>
          {mode === 'short' ? <code className={styles['short-uuid']}>{shortUuid(id)}</code> : agent.name}
        </span>
      </Tooltip>
    );
  }

  // ─── Generic / manual name ───
  const resolvedName = name || (mode === 'short' ? shortUuid(id) : id);
  const isRawUuid = !name;

  const tooltipContent = (
    <div className={styles['tooltip-content']}>
      {type && <div className={styles['tooltip-type']}>{type}</div>}
      {name && <div className={styles['tooltip-name']}>{name}</div>}
      <code className={styles['tooltip-id']}>{id}</code>
      {meta && <div className={styles['tooltip-meta']}>{meta}</div>}
    </div>
  );

  return (
    <Tooltip content={tooltipContent} position={tooltipPosition}>
      <span className={isRawUuid ? styles.uuid : styles.name}>
        {resolvedName}
      </span>
    </Tooltip>
  );
}

export default EntityField;
