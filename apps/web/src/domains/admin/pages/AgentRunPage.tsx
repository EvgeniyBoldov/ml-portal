import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { agentRunsApi } from '@/shared/api/admin';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { Button } from '@/shared/ui';
import { ExecutionTrace, downloadTraceLog } from '@/domains/sandbox/components/ExecutionTrace';
import { TraceInspector } from '@/domains/sandbox/components/traceInspector/TraceInspector';
import { replayRuntimeJournal } from '@/domains/sandbox/traceState';
import { resolveTraceInspectionTarget, traceElapsedMs, type TraceInspectionTarget } from '@/domains/sandbox/traceProjection';
import { agentRunTraceEvents } from '../agentRunTrace';

export default function AgentRunPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [target, setTarget] = useState<TraceInspectionTarget | null>(null);
  const { data: run, isLoading } = useQuery({ queryKey: ['admin', 'agent-runs', id], queryFn: () => agentRunsApi.get(id), enabled: Boolean(id) });
  const rawTrace = useMemo(() => replayRuntimeJournal(run?.events ?? []), [run]);
  const trace = useMemo(() => replayRuntimeJournal(run ? agentRunTraceEvents(run) : []), [run]);
  const selectedTarget = target ? resolveTraceInspectionTarget(trace, target.key) ?? target : null;
  const agentEntity = trace.rootEntityKey ? trace.entitiesByKey[trace.rootEntityKey]
    : Object.values(trace.entitiesByKey).find((entity) => entity.type === 'agent_execution');
  const inferredAgentName = agentEntity?.eventIds.map((eventId) => trace.eventsById[eventId]?.payload.agent_slug)
    .find((value): value is string => typeof value === 'string' && Boolean(value)) || 'Запуск агента';
  const agentName = run?.agent_name || inferredAgentName;
  const agentSlug = run?.agent_slug || inferredAgentName;
  const breadcrumbs: BreadcrumbItem[] = [{ label: 'Запуски агентов', href: '/admin/agent-runs' }, { label: id }];
  return (
    <EntityPageV2 title={agentName} subtitle={agentSlug} mode="view" breadcrumbs={breadcrumbs} backPath="/admin/agent-runs" loading={isLoading}
      headerActions={<Button onClick={() => downloadTraceLog(rawTrace, [], traceElapsedMs(rawTrace, Date.now()))} disabled={!run?.events.length}>Скачать лог</Button>}>
      <Tab title="Трейс" id="trace" layout="custom">
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(340px, 32%)', gap: 16, minHeight: 600 }}>
          <section style={{ minWidth: 0, border: '1px solid var(--border)', borderRadius: 8, padding: 12, overflow: 'auto' }}>
            {run ? <ExecutionTrace trace={trace} rawEvents={rawTrace} showHeader={false} isRunning={false} defaultExpanded defaultCallsExpanded onSelectTarget={setTarget} selectedTargetKey={selectedTarget?.key} /> : null}
          </section>
          <aside style={{ minWidth: 0, border: '1px solid var(--border)', borderRadius: 8, padding: 12, overflow: 'auto' }}>
            {selectedTarget ? <TraceInspector target={selectedTarget} trace={trace} /> : <p style={{ color: 'var(--muted)' }}>Выберите элемент трейса для просмотра деталей.</p>}
          </aside>
        </div>
      </Tab>
    </EntityPageV2>
  );
}
