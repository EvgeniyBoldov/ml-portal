import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { memoryJobsApi, type MemoryJobDetail } from '@/shared/api/admin';
import { consumeSse } from '@/shared/api/sse';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { Button } from '@/shared/ui';
import { ExecutionTrace, downloadTraceLog } from '@/domains/sandbox/components/ExecutionTrace';
import { TraceInspector } from '@/domains/sandbox/components/traceInspector/TraceInspector';
import { replayRuntimeJournal } from '@/domains/sandbox/traceState';
import { resolveTraceInspectionTarget, traceElapsedMs, type TraceInspectionTarget } from '@/domains/sandbox/traceProjection';
import { normalizeAgentRunEvents } from '../agentRunTrace';

const activeStatuses = new Set(['queued', 'screening', 'studying', 'conflict_checking']);

function parseJournal(data: string): MemoryJobDetail['events'][number] | null {
  try {
    const value = JSON.parse(data) as Record<string, unknown>;
    if (typeof value.id !== 'string' || typeof value.run_id !== 'string' || typeof value.sequence !== 'number' || typeof value.event_type !== 'string' || typeof value.occurred_at !== 'string' || !value.payload || typeof value.payload !== 'object') return null;
    return value as MemoryJobDetail['events'][number];
  } catch {
    return null;
  }
}

export default function MemoryJobPage() {
  const { id = '' } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<TraceInspectionTarget | null>(null);
  const { data: job, isLoading } = useQuery({
    queryKey: ['admin', 'memory-jobs', id], queryFn: () => memoryJobsApi.get(id), enabled: Boolean(id),
    refetchInterval: (query) => activeStatuses.has(query.state.data?.status || '') ? 5_000 : false,
  });

  useEffect(() => {
    if (!id || !job?.trace_run_id || !activeStatuses.has(job.status)) return;
    const controller = new AbortController();
    void memoryJobsApi.stream(id, controller.signal).then(async (response) => {
      if (!response.ok) throw new Error(`Memory trace stream failed: ${response.status}`);
      await consumeSse(response, (frame) => {
        if (frame.event !== 'journal') return;
        const event = parseJournal(frame.data);
        if (!event) return;
        queryClient.setQueryData<MemoryJobDetail>(['admin', 'memory-jobs', id], (current) => {
          if (!current || current.events.some((item) => item.id === event.id)) return current;
          return { ...current, events: [...current.events, event] };
        });
      });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) console.warn('Memory trace stream disconnected', error);
    });
    return () => controller.abort();
  }, [id, job?.status, job?.trace_run_id, queryClient]);

  const rawTrace = useMemo(() => replayRuntimeJournal(job ? normalizeAgentRunEvents(job.events) : []), [job]);
  const trace = rawTrace;
  const selectedTarget = target ? resolveTraceInspectionTarget(trace, target.key) ?? target : null;
  const breadcrumbs: BreadcrumbItem[] = [{ label: 'Запуски агентов', href: '/admin/agent-runs' }, { label: 'Мемори' }, { label: id }];
  const title = job?.document_title || job?.document_filename || 'Извлечение памяти';
  return (
    <EntityPageV2 title={title} subtitle={job?.trace_run_id || 'Ожидание запуска'} mode="view" breadcrumbs={breadcrumbs} backPath="/admin/agent-runs" loading={isLoading}
      headerActions={<Button onClick={() => downloadTraceLog(rawTrace, [], traceElapsedMs(rawTrace, Date.now()))} disabled={!job?.events.length}>Скачать лог</Button>}>
      <Tab title="Трейс" id="trace" layout="custom">
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(340px, 32%)', gap: 16, minHeight: 600 }}>
          <section style={{ minWidth: 0, border: '1px solid var(--border)', borderRadius: 8, padding: 12, overflow: 'auto' }}>
            {job ? <ExecutionTrace trace={trace} rawEvents={rawTrace} showHeader={false} isRunning={activeStatuses.has(job.status)} defaultExpanded defaultCallsExpanded onSelectTarget={setTarget} selectedTargetKey={selectedTarget?.key} /> : null}
          </section>
          <aside style={{ minWidth: 0, border: '1px solid var(--border)', borderRadius: 8, padding: 12, overflow: 'auto' }}>
            {selectedTarget ? <TraceInspector target={selectedTarget} trace={trace} /> : <p style={{ color: 'var(--muted)' }}>Выберите этап или LLM-вызов для просмотра деталей.</p>}
          </aside>
        </div>
      </Tab>
    </EntityPageV2>
  );
}
