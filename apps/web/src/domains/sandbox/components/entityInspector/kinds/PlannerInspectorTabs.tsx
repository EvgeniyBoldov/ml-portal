import Badge from '@/shared/ui/Badge';
import { InspectorFieldGroup, InspectorFieldRow, InspectorNotice, InspectorTabs } from '@/shared/ui/Inspector';
import { isPlannerData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, formatDuration, RawTab } from '../shared';

const PLANNER_ACTION_LABELS: Record<string, string> = {
  call_agent: 'Вызвать агента',
  agent_call: 'Вызвать агента',
  final: 'Ответ пользователю',
  direct_answer: 'Ответ пользователю',
  ask_user: 'Уточнить у пользователя',
  clarify: 'Уточнить у пользователя',
  abort: 'Прервать выполнение',
};

const RISK_TONE: Record<string, 'neutral' | 'success' | 'warn' | 'danger' | 'info'> = {
  low: 'success',
  medium: 'warn',
  high: 'danger',
};

function PlannerInfoTab({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isPlannerData(entity.data) ? entity.data : null;
  const source = steps.filter((s) => entity.sourceEventIds.includes(s.id));

  const thinking = source.find((s) => s.type === 'status' && String((s.data as Record<string, unknown>).stage ?? '') === 'planner_thinking');
  const decision = source.find((s) => s.type === 'planner_step');
  const decisionData = (decision?.data ?? {}) as Record<string, unknown>;
  const envelope = (decisionData._envelope ?? {}) as Record<string, unknown>;

  const actionKey = String(data?.stepKind ?? decisionData.kind ?? 'planner_step');
  const actionLabel = PLANNER_ACTION_LABELS[actionKey] ?? actionKey;
  const risk = String(decisionData.risk ?? 'unknown');
  const plannerIterationId = String(decisionData.planner_iteration_id ?? (thinking?.data as Record<string, unknown> | undefined)?.planner_iteration_id ?? '—');
  const plannerRunId = String(decisionData.planner_run_id ?? (thinking?.data as Record<string, unknown> | undefined)?.planner_run_id ?? '—');
  const sequence = String(envelope.sequence ?? '—');
  const agentSlug = String(decisionData.agent_slug ?? data?.decision?.chosenAgentSlug ?? '—');

  return (
    <InspectorFieldGroup>
      <InspectorFieldRow label="Этап">Планирование</InspectorFieldRow>
      <InspectorFieldRow label="Статусы">Думал → Решил</InspectorFieldRow>
      <InspectorFieldRow label="Действие">{actionLabel}</InspectorFieldRow>
      <InspectorFieldRow label="Цель">{agentSlug !== '—' && agentSlug !== 'null' ? `Агент: ${agentSlug}` : 'Пользователь'}</InspectorFieldRow>
      <InspectorFieldRow label="Риск"><Badge tone={RISK_TONE[risk] ?? 'neutral'} size="sm">{risk}</Badge></InspectorFieldRow>
      <InspectorFieldRow label="Длительность">{formatDuration(entity.durationMs)}</InspectorFieldRow>
      <InspectorFieldRow label="Итерация">{plannerIterationId}</InspectorFieldRow>
      <InspectorFieldRow label="Planner Run">{plannerRunId}</InspectorFieldRow>
      <InspectorFieldRow label="Sequence">{sequence}</InspectorFieldRow>
    </InspectorFieldGroup>
  );
}

function PlannerDecisionTab({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isPlannerData(entity.data) ? entity.data : null;
  const source = steps.filter((s) => entity.sourceEventIds.includes(s.id));
  const decision = source.find((s) => s.type === 'planner_step');
  const decisionData = (decision?.data ?? {}) as Record<string, unknown>;
  const actionKey = String(data?.stepKind ?? decisionData.kind ?? 'planner_step');
  const actionLabel = PLANNER_ACTION_LABELS[actionKey] ?? actionKey;
  const agentSlug = String(decisionData.agent_slug ?? data?.decision?.chosenAgentSlug ?? '—');
  const phaseId = String(decisionData.phase_id ?? '—');

  return (
    <InspectorFieldGroup>
      <InspectorFieldRow label="Решение">{actionLabel}</InspectorFieldRow>
      <InspectorFieldRow label="Тип действия"><code>{actionKey}</code></InspectorFieldRow>
      <InspectorFieldRow label="Целевой агент">{agentSlug !== 'null' ? agentSlug : '—'}</InspectorFieldRow>
      <InspectorFieldRow label="Phase ID">{phaseId !== 'null' ? phaseId : '—'}</InspectorFieldRow>
    </InspectorFieldGroup>
  );
}

function PlannerRationaleTab({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isPlannerData(entity.data) ? entity.data : null;
  const source = steps.filter((s) => entity.sourceEventIds.includes(s.id));
  const decision = source.find((s) => s.type === 'planner_step');
  const decisionData = (decision?.data ?? {}) as Record<string, unknown>;
  const rationale = String(data?.rationale ?? decisionData.rationale ?? '').trim();

  return (
    <InspectorFieldGroup>
      <InspectorFieldRow label="Обоснование">
        <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.45 }}>{rationale || '—'}</div>
      </InspectorFieldRow>
    </InspectorFieldGroup>
  );
}

function PlannerRbacTab({ steps }: { steps: RunStep[] }) {
  const snapshot = [...steps]
    .reverse()
    .find((s) => s.type === 'status' && String(s.data.stage ?? '') === 'planner_rbac_snapshot');

  const rbac = (snapshot?.data.rbac ?? null) as Record<string, unknown> | null;
  if (!rbac) {
    return <InspectorNotice tone="neutral" title="RBAC Snapshot" message="Снимок RBAC для планера не найден" />;
  }

  const candidates = Array.isArray(rbac.candidates) ? rbac.candidates.map(String) : [];
  const allowed = Array.isArray(rbac.allowed) ? rbac.allowed.map(String) : [];
  const denied = Array.isArray(rbac.denied_by_rbac) ? rbac.denied_by_rbac.map(String) : [];

  return (
    <InspectorFieldGroup>
      <InspectorFieldRow label="Кандидаты">{String(candidates.length)}</InspectorFieldRow>
      <InspectorFieldRow label="Доступно">{String(allowed.length)}</InspectorFieldRow>
      <InspectorFieldRow label="Срезано RBAC">{String(denied.length)}</InspectorFieldRow>
      <InspectorFieldRow label="Allowed">{allowed.length ? allowed.join(', ') : '—'}</InspectorFieldRow>
      <InspectorFieldRow label="Denied">{denied.length ? denied.join(', ') : '—'}</InspectorFieldRow>
    </InspectorFieldGroup>
  );
}

export function PlannerInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const tabs = [{ key: 'info', label: 'Info' }, { key: 'decision', label: 'Decision' }, { key: 'rationale', label: 'Rationale' }, { key: 'rbac', label: 'RBAC' }, { key: 'budgets', label: 'Budgets' }, { key: 'raw', label: 'Raw' }];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return <PlannerInfoTab entity={entity} steps={steps} />;
    if (tab === 'decision') return <PlannerDecisionTab entity={entity} steps={steps} />;
    if (tab === 'rationale') return <PlannerRationaleTab entity={entity} steps={steps} />;
    if (tab === 'rbac') return <PlannerRbacTab steps={steps} />;
    if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
