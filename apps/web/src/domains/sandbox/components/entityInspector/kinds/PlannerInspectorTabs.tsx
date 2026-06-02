import { InspectorFieldGroup, InspectorFieldRow, InspectorTabs } from '@/shared/ui/Inspector';
import { isPlannerData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, RawTab, SnapshotBadgeField, SnapshotTextField, SnapshotValueField, getEntityContextSnapshot } from '../shared';

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

const PLANNER_DECISION_TYPES = new Set(['planner_step', 'planner_action', 'planner_decision']);

function PlannerIntentTab({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isPlannerData(entity.data) ? entity.data : null;
  const snapshot = getEntityContextSnapshot(entity);
  const snapshotInputs = snapshot?.inputs;
  const snapshotMeta = snapshot?.meta;
  const availableAgents = Array.isArray(snapshotMeta?.available_agents) ? snapshotMeta.available_agents.map(String) : [];
  const facts = typeof snapshotMeta?.memory_digest?.facts === 'number' ? snapshotMeta.memory_digest.facts : undefined;
  const summaryChars = typeof snapshotMeta?.memory_digest?.summary_chars === 'number' ? snapshotMeta.memory_digest.summary_chars : undefined;

  return (
    <InspectorFieldGroup>
      <SnapshotTextField label="Намерение" text={String(snapshotInputs?.iteration_intent ?? data?.rationale ?? '—')} />
      <SnapshotValueField label="Попытка" value={snapshotMeta?.attempt ?? '—'} />
      <SnapshotValueField label="Максимум попыток" value={snapshotMeta?.max_attempts ?? '—'} />
      <SnapshotValueField label="Фактов в памяти" value={facts ?? '—'} />
      <SnapshotValueField label="Размер summary" value={summaryChars ?? '—'} />
      <InspectorFieldRow label="Доступные агенты">{availableAgents.length ? availableAgents.join(', ') : '—'}</InspectorFieldRow>
    </InspectorFieldGroup>
  );
}

function PlannerDecisionTab({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isPlannerData(entity.data) ? entity.data : null;
  const source = steps;
  const decision = source.find((s) => PLANNER_DECISION_TYPES.has(s.type));
  const decisionData = (decision?.data ?? {}) as Record<string, unknown>;
  const actionKey = String(data?.stepKind ?? decisionData.kind ?? 'planner_decision');
  const actionLabel = PLANNER_ACTION_LABELS[actionKey] ?? actionKey;
  const agentSlug = String(decisionData.agent_slug ?? data?.decision?.chosenAgentSlug ?? '—');
  const phaseId = String(decisionData.phase_id ?? '—');

  return (
    <InspectorFieldGroup>
      <SnapshotValueField label="Решение" value={actionLabel} />
      <SnapshotValueField label="Тип действия" value={actionKey} />
      <SnapshotValueField label="Целевой агент" value={agentSlug !== 'null' ? agentSlug : '—'} />
      <SnapshotValueField label="Фаза" value={phaseId !== 'null' ? phaseId : '—'} />
      <SnapshotBadgeField label="Риск" tone={RISK_TONE[String(decisionData.risk ?? 'unknown')] ?? 'neutral'} text={String(decisionData.risk ?? 'unknown')} />
      <InspectorFieldRow label="Обоснование">{String(data?.rationale ?? decisionData.rationale ?? '—')}</InspectorFieldRow>
    </InspectorFieldGroup>
  );
}

export function PlannerInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const tabs = [
    { key: 'intent', label: 'Намерение' },
    { key: 'decision', label: 'Решение' },
    { key: 'budgets', label: 'Бюджет' },
    { key: 'raw', label: 'RAW' },
  ];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'intent') return <PlannerIntentTab entity={entity} steps={steps} />;
    if (tab === 'decision') return <PlannerDecisionTab entity={entity} steps={steps} />;
    if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
