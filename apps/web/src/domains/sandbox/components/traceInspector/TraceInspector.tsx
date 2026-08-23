import { InspectorFieldGroup, InspectorFieldRow, InspectorHeader, InspectorJsonBlock, InspectorPanel, InspectorScalar, InspectorStatus, InspectorTabs } from '@/shared/ui/Inspector';
import type { SandboxTraceState } from '../../traceState';
import type { TraceInspectionTarget } from '../../traceProjection';
import { PlanView, TextValue } from './TraceDataViews';
import { CallInfoView, LlmErrorView, LlmInfoView, LlmRequestSnapshotView, LlmResponseSnapshotView, ToolInfoView, ToolRequestView, ToolResponseView } from './CallViews';
import { ExecutorResultView, StageResultView, StepResultView } from './ResultViews';
import { callDisplayName, llmResponseContent, toDisplayEntries } from '../../callInspection';
import { callPresentation, formatCallDuration } from '../../callPresentation';
import type { ToolNameMap } from '../../callInspection';
import { projectPlan, projectPlanTask, taskStatusLabel, type PlanTaskViewModel } from '../../planInspection';
import { PlanTaskCard } from './PlanTaskCard';
import { traceStatusLabel, traceStatusTone } from '../../traceStatus';
import { FactsViewer, LimitsViewer, MemoryContextViewer, PreflightViewer, PromptViewer, RawEventsViewer, RbacViewer } from './viewers';

interface Props { target: TraceInspectionTarget | null; trace: SandboxTraceState | null; toolNames?: ToolNameMap; }
const eventPayloads = (state: SandboxTraceState | null, ids: string[]) => ids.map((id) => state?.eventsById[id]?.payload).filter(Boolean);
const latestEntityPayload = (state: SandboxTraceState | null, entityId: string, eventType: string): Record<string, unknown> | undefined => {
  const entity = state?.entitiesByKey[entityId];
  if (!entity) return undefined;
  return [...entity.eventIds].reverse()
    .map((id) => state?.eventsById[id])
    .find((event) => event?.event_type === eventType)?.payload;
};
function statusTone(status: string): 'neutral' | 'success' | 'warn' | 'danger' | 'info' {
  return traceStatusTone(status);
}

export function TraceInspector({ target, trace, toolNames }: Props) {
  if (!target) return null;
  const entity = target.kind === 'iteration' ? target.stage.entity
    : target.kind === 'step' ? target.step.entity
      : target.kind === 'call' || target.kind === 'error' ? target.call.entity
      : target.executor.entity;
  const title = target.kind === 'iteration' ? target.stage.label
    : target.kind === 'step' ? target.step.title
      : target.kind === 'executor_run' ? target.executor.executorName
        : target.call.kind === 'tool' ? callDisplayName(String(target.call.request.payload.tool ?? ''), toolNames) : target.call.title;
  const kindLabel = { iteration: 'Этап', step: 'Шаг', executor_run: 'Запуск исполнителя', call: 'Вызов', error: 'Ошибка' }[target.kind];
  const payloads = eventPayloads(trace, entity.eventIds);
  const stage = target.kind === 'iteration' ? target.stage : target.kind === 'step' ? target.step.stage : target.stage;
  const runBudgetSnapshot = trace?.runId
    ? latestEntityPayload(trace, `run:${trace.runId}`, 'budget_snapshot')
    : undefined;
  const plannerExecutorIds = new Set(stage.executorRuns.filter((item) => item.executorSlug === 'planner').map((item) => item.entity.id));
  const journalEvents = Object.values(trace?.eventsById ?? {});
  const planEvent = journalEvents
    .filter((event) => event.event_type === 'plan_created' || event.event_type === 'plan_patch_applied')
    .filter((event) => plannerExecutorIds.has(event.parent_entity_id ?? ''))
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
  const planTasks = projectPlan(plan).tasks;
  const selectedPlanTask = (taskId: string | undefined): PlanTaskViewModel | undefined => (
    taskId ? planTasks.find((task) => task.taskId === taskId) : undefined
  );
  const selectedTask = (() => {
    if (target.kind === 'step') {
      const runtimeExecutor = target.step.executorRuns[0];
      const runtimePayload = runtimeExecutor?.start.payload ?? {};
      const taskId = target.step.taskId ?? (typeof runtimePayload.task_id === 'string' ? runtimePayload.task_id : undefined);
      const plannedTask = selectedPlanTask(taskId);
      if (plannedTask) {
        return {
          ...plannedTask,
          title: target.step.title || plannedTask.title,
          objective: target.step.objective ?? plannedTask.objective,
          executor: plannedTask.executor ?? runtimeExecutor?.executorSlug,
          status: plannedTask.status ?? taskStatusLabel(runtimeExecutor?.entity.status),
          inputs: target.step.inputs ?? plannedTask.inputs,
        };
      }
      return projectPlanTask({
        task_id: taskId,
        title: target.step.title,
        objective: target.step.objective,
        inputs: target.step.inputs,
        executor: runtimeExecutor?.executorSlug,
        status: taskStatusLabel(runtimeExecutor?.entity.status),
      }, taskId ?? 'step-task');
    }
    if (target.kind === 'executor_run') {
      const runtimePayload = target.executor.start.payload;
      const taskId = typeof runtimePayload.task_id === 'string' ? runtimePayload.task_id : undefined;
      const plannedTask = selectedPlanTask(taskId);
      if (plannedTask) {
        return {
          ...plannedTask,
          title: target.executor.task || plannedTask.title,
          objective: typeof runtimePayload.task_objective === 'string' ? runtimePayload.task_objective : plannedTask.objective,
          executor: plannedTask.executor ?? target.executor.executorSlug,
          status: plannedTask.status ?? taskStatusLabel(target.executor.entity.status),
          inputs: runtimePayload.task_inputs ?? plannedTask.inputs,
          instructions: typeof runtimePayload.instructions === 'string' ? runtimePayload.instructions : plannedTask.instructions,
        };
      }
      return projectPlanTask({
        task_id: taskId,
        title: target.executor.task,
        objective: runtimePayload.task_objective,
        instructions: runtimePayload.instructions,
        inputs: runtimePayload.task_inputs,
        executor: target.executor.executorSlug,
        status: taskStatusLabel(target.executor.entity.status),
      }, taskId ?? target.executor.entity.id);
    }
    return undefined;
  })();
  const targetMetrics = target.kind === 'iteration' ? target.stage.metrics
    : target.kind === 'step' ? target.step.metrics
      : target.kind === 'executor_run' ? target.executor.metrics
        : undefined;
  const selectedCallPresentation = target.kind === 'call' || target.kind === 'error'
    ? callPresentation(target.call)
    : undefined;
  const callHasError = selectedCallPresentation?.status === 'error';
  const hasPlanTab = target.kind === 'iteration' && stage.executorRuns.some((executor) => executor.executorSlug === 'planner');
  const common = <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label={traceStatusLabel(entity.status)} tone={statusTone(entity.status)} /></InspectorFieldRow>
    {targetMetrics?.elapsedMs ? <InspectorFieldRow label="Длительность"><InspectorScalar value={`${(targetMetrics.elapsedMs / 1000).toFixed(1)} с`} /></InspectorFieldRow> : null}
    {targetMetrics?.calls ? <InspectorFieldRow label="Вызовы"><InspectorScalar value={targetMetrics.calls} /></InspectorFieldRow> : null}
    {targetMetrics?.successfulCalls ? <InspectorFieldRow label="Успешно"><InspectorScalar value={targetMetrics.successfulCalls} /></InspectorFieldRow> : null}
    {targetMetrics?.failedCalls ? <InspectorFieldRow label="Ошибки"><InspectorScalar value={targetMetrics.failedCalls} /></InspectorFieldRow> : null}
    {targetMetrics?.tokens ? <InspectorFieldRow label="Токены"><InspectorScalar value={targetMetrics.tokens} /></InspectorFieldRow> : null}
    {targetMetrics?.retries ? <InspectorFieldRow label="Повторы"><InspectorScalar value={targetMetrics.retries} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
  const tabs = target.kind === 'call' && target.call.kind === 'llm' ? [{ key: 'info', label: 'Инфо' }, { key: 'request', label: 'Запрос' }, { key: callHasError ? 'error' : 'response', label: callHasError ? 'Ошибка' : 'Результат' }, { key: 'raw', label: 'RAW' }]
    : target.kind === 'iteration' ? [{ key: 'info', label: 'Инфо' }, ...(hasPlanTab ? [{ key: 'plan', label: 'План' }] : []), { key: 'result', label: 'Итоги' }, { key: 'raw', label: 'RAW' }]
    : target.kind === 'step' ? [{ key: 'info', label: 'Инфо' }, { key: 'task', label: 'Задача' }, { key: 'result', label: 'Результат' }, { key: 'raw', label: 'RAW' }]
      : target.kind === 'executor_run' ? [
        { key: 'info', label: 'Инфо' },
        ...(target.executor.executorSlug === 'planner' ? [{ key: 'plan', label: 'План' }]
          : target.executor.executorSlug === 'synthesizer' ? [{ key: 'result', label: 'Результат' }]
            : target.executor.executorSlug === 'memory_preparation'
              ? [{ key: 'task', label: 'Задача' }, { key: 'memory', label: 'Memory' }]
              : target.executor.executorSlug === 'fact_extractor' || target.executor.executorSlug === 'fact_compactor'
              ? [{ key: 'task', label: 'Задача' }, { key: 'facts', label: target.executor.executorSlug === 'fact_compactor' ? 'Изменения' : 'Факты' }]
              : [{ key: 'task', label: 'Задача' }, { key: 'result', label: 'Результат' }]),
        { key: 'prompt', label: 'Prompt' },
        { key: 'rbac', label: 'RBAC' },
        { key: 'limits', label: 'Лимиты' },
        { key: 'preflight', label: 'Preflight' },
        { key: 'raw', label: 'RAW' },
      ]
        : target.kind === 'error' ? [{ key: 'info', label: 'Инфо' }, { key: 'error', label: 'Ошибка' }, { key: 'raw', label: 'RAW' }]
          : [{ key: 'info', label: 'Инфо' }, { key: 'request', label: 'Запрос' }, { key: callHasError ? 'error' : 'response', label: callHasError ? 'Ошибка' : 'Результат' }, { key: 'raw', label: 'RAW' }];
  const render = (tab: string) => {
    if (tab === 'info' && target.kind === 'call' && target.call.kind === 'llm') return <LlmInfoView call={target.call} />;
    if (tab === 'info' && target.kind === 'call' && target.call.kind === 'tool') return <ToolInfoView call={target.call} toolNames={toolNames} description={target.executor.task} />;
    if (tab === 'info' && target.kind === 'call') return <CallInfoView call={target.call} />;
    if (tab === 'info') return common;
    if (tab === 'plan') return <PlanView plan={plan} />;
    if (tab === 'task' && (target.kind === 'step' || target.kind === 'executor_run') && selectedTask) return <PlanTaskCard task={selectedTask} variant="compact" />;
    if (tab === 'facts' && target.kind === 'executor_run') return <FactsViewer result={target.executor.memoryResult} />;
    if (tab === 'memory' && target.kind === 'executor_run') return <MemoryContextViewer events={target.executor.entity.eventIds.map((id) => trace?.eventsById[id]).filter((event): event is NonNullable<typeof event> => Boolean(event))} />;
    if (tab === 'result' && target.kind === 'iteration') return <StageResultView stage={target.stage} trace={trace} />;
    if (tab === 'result' && target.kind === 'step') return <StepResultView step={target.step} trace={trace} />;
    if (tab === 'result' && target.kind === 'executor_run') return target.executor.executorSlug === 'planner' ? <PlanView plan={plan} /> : <ExecutorResultView executor={target.executor} trace={trace} />;
    if (tab === 'prompt' && target.kind === 'executor_run') return <PromptViewer prompt={target.executor.prompt} />;
    if (tab === 'rbac' && target.kind === 'executor_run') return <RbacViewer snapshot={target.executor.rbacSnapshot ?? target.executor.preflight?.rbacSnapshot} />;
    if (tab === 'limits' && target.kind === 'executor_run') return <LimitsViewer executorSnapshot={target.executor.limitsSnapshot} runSnapshot={runBudgetSnapshot} />;
    if (tab === 'preflight' && target.kind === 'executor_run') return <PreflightViewer preflight={target.executor.preflight} />;
    if (tab === 'error' && target.kind === 'call' && target.call.kind === 'llm') return <LlmErrorView call={target.call} />;
    if (tab === 'error' && (target.kind === 'error' || target.kind === 'call')) {
      const payload = target.call.response?.payload ?? target.call.request.payload;
      const error = selectedCallPresentation?.error;
      const entries = toDisplayEntries(payload).filter((entry) => ['Код ошибки', 'Сообщение', 'Статус', 'error', 'error type', 'retryable', 'recoverable', 'Можно повторить', 'Восстанавливаемая'].includes(entry.label) || entry.label.toLowerCase().includes('ошиб'));
      return <InspectorFieldGroup>
        <InspectorFieldRow label="Статус"><InspectorStatus label="Ошибка" tone="danger" /></InspectorFieldRow>
        {error ? <>
          <InspectorFieldRow label="Название ошибки"><InspectorScalar value={error.name} /></InspectorFieldRow>
          {error.code ? <InspectorFieldRow label="Код ошибки"><InspectorScalar value={error.code} /></InspectorFieldRow> : null}
          {error.message ? <InspectorFieldRow label="Сообщение"><InspectorScalar value={error.message} /></InspectorFieldRow> : null}
          {error.statusCode !== undefined ? <InspectorFieldRow label="HTTP-статус"><InspectorScalar value={error.statusCode} /></InspectorFieldRow> : null}
          {error.providerCode ? <InspectorFieldRow label="Код провайдера"><InspectorScalar value={error.providerCode} /></InspectorFieldRow> : null}
          {error.retryable !== undefined ? <InspectorFieldRow label="Можно повторить"><InspectorStatus label={error.retryable ? 'Да' : 'Нет'} tone={error.retryable ? 'warn' : 'neutral'} /></InspectorFieldRow> : null}
          {error.retryAfterMs !== undefined ? <InspectorFieldRow label="Повтор через"><InspectorScalar value={formatCallDuration(error.retryAfterMs)} /></InspectorFieldRow> : null}
        </> : entries.map((entry) => <TextValue key={entry.label} label={entry.label} value={entry.value} />)}
      </InspectorFieldGroup>;
    }
    if (tab === 'request' && target.kind === 'call') return target.call.kind === 'llm' ? <LlmRequestSnapshotView call={target.call} executionSnapshot={target.executor.prompt?.snapshot} /> : target.call.kind === 'tool' ? <ToolRequestView call={target.call} /> : <InspectorFieldGroup><TextValue label="Запрос" value={target.call.request.payload.question ?? target.call.request.payload.message} /></InspectorFieldGroup>;
    if (tab === 'response' && target.kind === 'call') return target.call.kind === 'llm' ? <LlmResponseSnapshotView call={target.call} toolNames={toolNames} /> : target.call.kind === 'tool' ? <ToolResponseView call={target.call} /> : <InspectorFieldGroup><TextValue label="Ответ" value={target.call.response?.payload.user_answer ?? target.call.response?.payload.answer ?? 'Ожидается'} /></InspectorFieldGroup>;
    if (tab === 'raw' && (target.kind === 'call' || target.kind === 'error')) {
      return <RawEventsViewer events={(selectedCallPresentation?.rawEvents ?? target.call.events).map((event) => ({ sequence: event.sequence, eventType: event.event_type, value: event }))} />;
    }
    if (tab === 'raw') return <RawEventsViewer events={entity.eventIds.map((id) => trace?.eventsById[id]).filter((event): event is NonNullable<typeof event> => Boolean(event)).map((event) => ({ sequence: event.sequence, eventType: event.event_type, value: event }))} />;
    return <InspectorFieldGroup><InspectorJsonBlock value={payloads} /></InspectorFieldGroup>;
  };
  return <InspectorPanel header={<InspectorHeader tone={traceStatusTone(entity.status)} kindLabel={kindLabel} title={title} />}><InspectorTabs entityId={target.key} tabs={tabs} render={render} /></InspectorPanel>;
}
