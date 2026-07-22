import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorPanel, InspectorHeader, InspectorTabs, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { SandboxTraceState } from '../../traceState';
import type { TraceInspectionTarget } from '../../traceProjection';
import { LimitsView, PlanView, RbacView, TextValue } from './TraceDataViews';

interface Props { target: TraceInspectionTarget | null; trace: SandboxTraceState | null; }
const eventPayloads = (state: SandboxTraceState | null, ids: string[]) => ids.map((id) => state?.eventsById[id]?.payload).filter(Boolean);
const tone = (status: string): 'neutral' | 'success' | 'warn' | 'danger' | 'info' => status === 'error' || status === 'failed' ? 'danger' : status === 'completed' ? 'success' : 'info';

export function TraceInspector({ target, trace }: Props) {
  if (!target) return null;
  const entity = target.kind === 'iteration' ? target.stage.entity
    : target.kind === 'step' ? target.step.stage.entity
      : target.executor.entity;
  const title = target.kind === 'iteration' ? target.stage.label
    : target.kind === 'step' ? target.step.title
      : target.kind === 'executor_run' ? target.executor.executorName
        : target.call.title;
  const kindLabel = { iteration: 'Итерация', step: 'Степ', executor_run: 'Ранс исполнителя', call: 'Вызов', error: 'Ошибка' }[target.kind];
  const payloads = eventPayloads(trace, entity.eventIds);
  const snapshot = payloads.find((value) => value && typeof value === 'object' && ('context_snapshot' in value || 'rbac' in value || 'limits' in value)) ?? {};
  const stage = target.kind === 'iteration' ? target.stage : target.kind === 'step' ? target.step.stage : target.stage;
  const plannerExecutorIds = new Set(stage.executorRuns.filter((item) => item.executorSlug === 'planner').map((item) => item.entity.id));
  const plan = Object.values(trace?.eventsById ?? {}).find((event) => (
    event.entity_type === 'plan'
    && plannerExecutorIds.has(event.parent_entity_id ?? '')
  ))?.payload ?? payloads.find((value) => value && typeof value === 'object' && ('patch' in value || 'revision' in value || 'plan_id' in value)) ?? {};
  const common = <InspectorFieldGroup><InspectorFieldRow label="Статус">{entity.status}</InspectorFieldRow><InspectorFieldRow label="ID"><code>{entity.id}</code></InspectorFieldRow></InspectorFieldGroup>;
  const tabs = target.kind === 'iteration' ? [{ key: 'info', label: 'Инфо' }, { key: 'plan', label: 'План' }, { key: 'raw', label: 'RAW' }]
    : target.kind === 'step' ? [{ key: 'info', label: 'Инфо' }, { key: 'task', label: 'Задача' }, { key: 'result', label: 'Результат' }, { key: 'raw', label: 'RAW' }]
      : target.kind === 'executor_run' ? [{ key: 'info', label: 'Инфо' }, { key: 'task', label: 'Задача' }, { key: 'result', label: 'Результат' }, { key: 'executor', label: 'Исполнитель' }, { key: 'limits', label: 'Лимиты' }, { key: 'rbac', label: 'RBAC' }, { key: 'raw', label: 'RAW' }]
        : target.kind === 'error' ? [{ key: 'info', label: 'Инфо' }, { key: 'error', label: 'Ошибка' }, { key: 'context', label: 'Контекст' }, { key: 'raw', label: 'RAW' }]
          : [{ key: 'info', label: 'Инфо' }, { key: 'request', label: 'Реквест' }, { key: 'response', label: 'Респонс' }, { key: 'raw', label: 'RAW' }];
  const render = (tab: string) => {
    if (tab === 'info') return common;
    if (tab === 'plan') return <PlanView plan={plan} />;
    if (tab === 'task' && target.kind === 'step') return <InspectorFieldGroup><TextValue label="Задача" value={target.step.title} /><TextValue label="Цель" value={target.step.objective} /><InspectorFieldRow label="Вход"><InspectorJsonBlock value={target.step.inputs ?? '—'} /></InspectorFieldRow></InspectorFieldGroup>;
    if (tab === 'task' && target.kind === 'executor_run') return <InspectorFieldGroup><TextValue label="Задача" value={target.executor.task} /><InspectorFieldRow label="Вход"><InspectorJsonBlock value={target.executor.start.payload.task_inputs ?? '—'} /></InspectorFieldRow></InspectorFieldGroup>;
    if (tab === 'result') return <InspectorFieldGroup><InspectorFieldRow label="Результат"><InspectorJsonBlock value={payloads[payloads.length - 1] ?? '—'} /></InspectorFieldRow></InspectorFieldGroup>;
    if (tab === 'executor' && target.kind === 'executor_run') return <InspectorFieldGroup><InspectorFieldRow label="Тип">{target.executor.executorType}</InspectorFieldRow><InspectorFieldRow label="Slug">{target.executor.executorSlug}</InspectorFieldRow><TextValue label="Промпт" value={(snapshot as Record<string, unknown>).system_prompt ?? (snapshot as Record<string, unknown>).prompt} /></InspectorFieldGroup>;
    if (tab === 'limits') return <LimitsView snapshot={snapshot} />;
    if (tab === 'rbac') return <RbacView snapshot={snapshot} />;
    if (tab === 'error' && target.kind === 'error') return <InspectorFieldGroup><TextValue label="Сообщение" value={target.call.request.payload.error ?? target.call.request.payload.message} /><InspectorFieldRow label="Детали"><InspectorJsonBlock value={target.call.request.payload} /></InspectorFieldRow></InspectorFieldGroup>;
    if (tab === 'context' && target.kind === 'error') return <InspectorFieldGroup><InspectorFieldRow label="Контекст"><InspectorJsonBlock value={target.call.request.payload.context ?? target.call.request.payload.debug ?? '—'} /></InspectorFieldRow></InspectorFieldGroup>;
    if (tab === 'request' && (target.kind === 'call' || target.kind === 'error')) return <InspectorFieldGroup><InspectorFieldRow label="Реквест"><InspectorJsonBlock value={target.call.request.payload} /></InspectorFieldRow></InspectorFieldGroup>;
    if (tab === 'response' && (target.kind === 'call' || target.kind === 'error')) return <InspectorFieldGroup><InspectorFieldRow label="Респонс">{target.call.response ? <InspectorJsonBlock value={target.call.response.payload} /> : <InspectorTextBlock text="Ожидается" />}</InspectorFieldRow></InspectorFieldGroup>;
    return <InspectorFieldGroup><InspectorJsonBlock value={payloads} /></InspectorFieldGroup>;
  };
  return <InspectorPanel header={<InspectorHeader tone={tone(entity.status)} kindLabel={kindLabel} title={title} />}><InspectorTabs entityId={target.key} tabs={tabs} render={render} /></InspectorPanel>;
}
