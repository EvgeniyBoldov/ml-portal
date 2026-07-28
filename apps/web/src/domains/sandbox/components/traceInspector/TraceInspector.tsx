import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar, InspectorPanel, InspectorHeader, InspectorTabs } from '@/shared/ui/Inspector';
import type { SandboxTraceState } from '../../traceState';
import type { TraceInspectionTarget } from '../../traceProjection';
import { ExecutorSnapshotView, LimitsView, PlanView, RbacView, TextValue } from './TraceDataViews';
import { CallInfoView, LlmRequestView, LlmResponseView, ToolRequestView, ToolResponseView } from './CallViews';
import { ExecutorResultView, StageResultView } from './ResultViews';
import { callDisplayName, llmResponseContent, rawCallEvents, toDisplayEntries } from '../../callInspection';
import type { ToolNameMap } from '../../callInspection';
import { traceStatusLabel, traceStatusTone } from '../../traceStatus';

interface Props { target: TraceInspectionTarget | null; trace: SandboxTraceState | null; toolNames?: ToolNameMap; }
const eventPayloads = (state: SandboxTraceState | null, ids: string[]) => ids.map((id) => state?.eventsById[id]?.payload).filter(Boolean);
const latestEntityPayload = (state: SandboxTraceState | null, entityId: string, eventType: string): Record<string, unknown> | undefined => {
  const entity = state?.entitiesByKey[entityId];
  if (!entity) return undefined;
  return [...entity.eventIds].reverse()
    .map((id) => state?.eventsById[id])
    .find((event) => event?.event_type === eventType)?.payload;
};
const latestExecutorConfigSnapshot = (state: SandboxTraceState | null, entityId: string): Record<string, unknown> | undefined => {
  const entity = state?.entitiesByKey[entityId];
  if (!entity) return undefined;
  return [...entity.eventIds].reverse()
    .map((id) => state?.eventsById[id]?.payload)
    .find((payload): payload is Record<string, unknown> => Boolean(payload?.config_snapshot));
};
const typedValue = (value: unknown) => value && typeof value === 'object'
  ? <InspectorJsonBlock value={value} />
  : <InspectorScalar value={value as string | number | boolean | null | undefined} />;

export function TraceInspector({ target, trace, toolNames }: Props) {
  if (!target) return null;
  const entity = target.kind === 'iteration' ? target.stage.entity
    : target.kind === 'step' ? target.step.stage.entity
      : target.kind === 'call' || target.kind === 'error' ? target.call.entity
      : target.executor.entity;
  const title = target.kind === 'iteration' ? target.stage.label
    : target.kind === 'step' ? target.step.title
      : target.kind === 'executor_run' ? target.executor.executorName
        : target.call.kind === 'tool' ? callDisplayName(String(target.call.request.payload.tool ?? ''), toolNames) : target.call.title;
  const kindLabel = { iteration: 'Итерация', step: 'Степ', executor_run: 'Ранс исполнителя', call: 'Вызов', error: 'Ошибка' }[target.kind];
  const payloads = eventPayloads(trace, entity.eventIds);
  const contextSnapshot = payloads.find((value) => value && typeof value === 'object' && 'context_snapshot' in value) as Record<string, unknown> | undefined;
  const rbacSnapshot = payloads.find((value) => value && typeof value === 'object' && 'rbac' in value) as Record<string, unknown> | undefined;
  const limitsSnapshot = payloads.find((value) => value && typeof value === 'object' && ('limits' in value || 'runtime_limits' in value)) as Record<string, unknown> | undefined;
  const snapshot = contextSnapshot?.context_snapshot ?? contextSnapshot ?? {};
  const stage = target.kind === 'iteration' ? target.stage : target.kind === 'step' ? target.step.stage : target.stage;
  const executorBudgetSnapshot = target.kind === 'executor_run'
    ? latestEntityPayload(trace, target.executor.entity.key, 'budget_snapshot')
    : undefined;
  const executorRbacSnapshot = target.kind === 'executor_run'
    ? latestEntityPayload(trace, target.executor.entity.key, 'rbac_snapshot')
    : undefined;
  const executorConfigSnapshot = target.kind === 'executor_run'
    ? latestExecutorConfigSnapshot(trace, target.executor.entity.key)
    : undefined;
  const runBudgetSnapshot = trace?.runId
    ? latestEntityPayload(trace, `run:${trace.runId}`, 'budget_snapshot')
    : undefined;
  const plannerExecutorIds = new Set(stage.executorRuns.filter((item) => item.executorSlug === 'planner').map((item) => item.entity.id));
  const journalEvents = Object.values(trace?.eventsById ?? {});
  const stageEndSequence = stage.entity.eventIds
    .map((id) => trace?.eventsById[id]?.sequence ?? 0)
    .reduce((max, value) => Math.max(max, value), 0);
  const planEvent = journalEvents
    .filter((event) => event.event_type === 'plan_created' || event.event_type === 'plan_patch_applied')
    .filter((event) => plannerExecutorIds.has(event.parent_entity_id ?? '') || (event.sequence >= stage.start.sequence && event.sequence <= stageEndSequence))
    .sort((left, right) => right.sequence - left.sequence)[0];
  const plannerResponse = journalEvents
    .filter((event) => event.event_type === 'llm_response' && plannerExecutorIds.has(event.parent_entity_id ?? '') && event.payload.purpose === 'planning_decision')
    .sort((left, right) => right.sequence - left.sequence)[0];
  const rawPlan = planEvent?.payload
    ?? (plannerResponse ? llmResponseContent(plannerResponse.payload) : undefined)
    ?? payloads.find((value) => value && typeof value === 'object' && ('patch' in value || 'revision' in value || 'plan_id' in value))
    ?? {};
  const plan = rawPlan && typeof rawPlan === 'object' && !Array.isArray(rawPlan)
    ? (() => {
        const value = rawPlan as Record<string, unknown>;
        const patch = value.patch;
        return patch && typeof patch === 'object' && !Array.isArray(patch) && Array.isArray((patch as Record<string, unknown>).tasks)
          ? {
              ...value,
              ...(patch as Record<string, unknown>),
              tasks: ((patch as Record<string, unknown>).tasks as unknown[]).map((task) => {
                if (!task || typeof task !== 'object' || Array.isArray(task)) return task;
                const item = task as Record<string, unknown>;
                return {
                  ...item,
                  title: item.title ?? item.intent ?? item.task_id,
                  objective: item.objective ?? item.instructions,
                  agent_slug: item.agent_slug ?? item.executor,
                };
              }),
            }
          : value;
      })()
    : rawPlan;
  const common = <InspectorFieldGroup><InspectorFieldRow label="Статус">{traceStatusLabel(entity.status)}</InspectorFieldRow><InspectorFieldRow label="ID"><code>{entity.id}</code></InspectorFieldRow></InspectorFieldGroup>;
  const tabs = target.kind === 'iteration' ? [{ key: 'info', label: 'Инфо' }, { key: 'plan', label: 'План' }, { key: 'result', label: 'Результат' }, { key: 'raw', label: 'RAW' }]
    : target.kind === 'step' ? [{ key: 'info', label: 'Инфо' }, { key: 'task', label: 'Задача' }, { key: 'result', label: 'Результат' }, { key: 'raw', label: 'RAW' }]
      : target.kind === 'executor_run' ? [{ key: 'info', label: 'Инфо' }, { key: 'task', label: 'Задача' }, { key: 'result', label: 'Результат' }, { key: 'executor', label: 'Исполнитель' }, { key: 'limits', label: 'Лимиты' }, { key: 'rbac', label: 'RBAC' }, { key: 'raw', label: 'RAW' }]
        : target.kind === 'error' ? [{ key: 'info', label: 'Инфо' }, { key: 'error', label: 'Ошибка' }, { key: 'context', label: 'Контекст' }, { key: 'raw', label: 'RAW' }]
          : [{ key: 'info', label: 'Инфо' }, { key: 'request', label: 'Реквест' }, { key: 'response', label: 'Респонс' }, { key: 'raw', label: 'RAW' }];
  const render = (tab: string) => {
    if (tab === 'info' && target.kind === 'call') return <CallInfoView call={target.call} toolNames={toolNames} />;
    if (tab === 'info') return common;
    if (tab === 'plan') return <PlanView plan={plan} />;
    if (tab === 'task' && target.kind === 'step') return <InspectorFieldGroup><TextValue label="Задача" value={target.step.title} /><TextValue label="Цель" value={target.step.objective} /><InspectorFieldRow label="Вход">{typedValue(target.step.inputs)}</InspectorFieldRow></InspectorFieldGroup>;
    if (tab === 'task' && target.kind === 'executor_run') return <InspectorFieldGroup><TextValue label="Задача" value={target.executor.task} /><InspectorFieldRow label="Вход">{typedValue(target.executor.start.payload.task_inputs)}</InspectorFieldRow></InspectorFieldGroup>;
    if (tab === 'result' && target.kind === 'iteration') return <StageResultView stage={target.stage} trace={trace} />;
    if (tab === 'result' && target.kind === 'step') return <StageResultView stage={target.step.stage} trace={trace} />;
    if (tab === 'result' && target.kind === 'executor_run') return target.executor.executorSlug === 'planner' ? <PlanView plan={plan} /> : <ExecutorResultView executor={target.executor} trace={trace} />;
    if (tab === 'executor' && target.kind === 'executor_run') return <><InspectorFieldGroup><InspectorFieldRow label="Тип">{target.executor.executorType}</InspectorFieldRow><InspectorFieldRow label="Slug">{target.executor.executorSlug}</InspectorFieldRow></InspectorFieldGroup><ExecutorSnapshotView snapshot={executorConfigSnapshot ?? snapshot} /></>;
    if (tab === 'limits') return <LimitsView executorSnapshot={executorBudgetSnapshot ?? limitsSnapshot ?? snapshot} runSnapshot={runBudgetSnapshot} />;
    if (tab === 'rbac') return <RbacView snapshot={executorRbacSnapshot ?? rbacSnapshot ?? snapshot} />;
    if (tab === 'error' && target.kind === 'error') return <InspectorFieldGroup>{toDisplayEntries(target.call.request.payload).map((entry) => <TextValue key={entry.label} label={entry.label} value={entry.value} />)}</InspectorFieldGroup>;
    if (tab === 'context' && target.kind === 'error') return <InspectorFieldGroup><TextValue label="Контекст" value={target.call.request.payload.context ?? 'Нет дополнительного контекста'} /></InspectorFieldGroup>;
    if (tab === 'request' && target.kind === 'call') return target.call.kind === 'llm' ? <LlmRequestView call={target.call} /> : target.call.kind === 'tool' ? <ToolRequestView call={target.call} /> : <InspectorFieldGroup><TextValue label="Запрос" value={target.call.request.payload.question ?? target.call.request.payload.message} /></InspectorFieldGroup>;
    if (tab === 'response' && target.kind === 'call') return target.call.kind === 'llm' ? <LlmResponseView call={target.call} toolNames={toolNames} /> : target.call.kind === 'tool' ? <ToolResponseView call={target.call} /> : <InspectorFieldGroup><TextValue label="Ответ" value={target.call.response?.payload.user_answer ?? target.call.response?.payload.answer ?? 'Ожидается'} /></InspectorFieldGroup>;
    if (tab === 'raw' && (target.kind === 'call' || target.kind === 'error')) return <InspectorFieldGroup><InspectorJsonBlock value={rawCallEvents(target.call.request, target.call.response)} /></InspectorFieldGroup>;
    return <InspectorFieldGroup><InspectorJsonBlock value={payloads} /></InspectorFieldGroup>;
  };
  return <InspectorPanel header={<InspectorHeader tone={traceStatusTone(entity.status)} kindLabel={kindLabel} title={title} />}><InspectorTabs entityId={target.key} tabs={tabs} render={render} /></InspectorPanel>;
}
