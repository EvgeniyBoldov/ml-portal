/**
 * AgentRunPage - Детальная страница запуска агента
 */
import { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { agentRunsApi } from '@/shared/api/agentRuns';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { Badge, Button } from '@/shared/ui';
import { getStatusProps } from '@/shared/lib/statusConfig';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
import { buildRunTrace, normalizeTraceEvent } from '@/domains/runtimeTrace/normalize';
import { buildTraceDiagnostics } from '@/domains/runtimeTrace/components/TraceDiagnosticsSummary';
import { buildEntityTree, findEntityById } from '@/domains/runtimeTrace/buildEntityTree';
import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import { TraceTree } from '@/domains/sandbox/components/TraceTree';
import { EntityInspector } from '@/domains/sandbox/components/EntityInspector';
import type { RunStep } from '@/domains/sandbox/hooks/useSandboxRun';
import styles from './AgentRunPage.module.css';

function formatDuration(ms?: number): string {
  if (!ms) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function DiagnosticValue({ value }: { value: unknown }): React.ReactNode {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return `[${value.length} items]`;
  if (typeof value === 'object') {
    // Render object as key=value pairs for readability
    const entries = Object.entries(value).slice(0, 4); // max 4 fields
    const preview = entries.map(([k, v]) => {
      let vStr: string;
      if (v === null || v === undefined) vStr = 'null';
      else if (typeof v === 'string') vStr = v.length > 20 ? `${v.slice(0, 20)}...` : v;
      else if (typeof v === 'object') vStr = '[obj]';
      else vStr = String(v);
      return `${k}=${vStr}`;
    }).join(' · ');
    const more = Object.keys(value).length > 4 ? ' ...' : '';
    return preview + more;
  }
  return String(value);
}

function RunSummary({ run, diagnostics, trace }: { run?: { status: string; duration_ms?: number; error?: string }; diagnostics: { budgetEvents: number; llmCalls: number; operationCalls: number; failedOperations: number; runtimeErrors: Array<{ code: string; userMessage: string }> }; trace: { iterations: Array<{ events: unknown[] }> } }) {
  const isFailed = run?.status === 'failed' || run?.status === 'error' || diagnostics.runtimeErrors.length > 0;
  const isPartial = run?.status === 'partial';
  const statusTone = isFailed ? 'danger' : isPartial ? 'warn' : 'success';
  const statusLabel = isFailed ? 'Failed' : isPartial ? 'Partial' : 'Success';
  const totalSteps = trace.iterations.reduce((sum, it) => sum + it.events.length, 0);
  const totalIterations = trace.iterations.length;
  const firstError = diagnostics.runtimeErrors[0];

  return (
    <div className={`${styles['run-summary']} ${isFailed ? styles['run-summary-failed'] : ''}`}>
      <div className={styles['run-summary-header']}>
        <Badge tone={statusTone as 'success' | 'warn' | 'danger'}>{statusLabel}</Badge>
        <span className={styles['run-summary-duration']}>{formatDuration(run?.duration_ms)}</span>
      </div>
      <div className={styles['run-summary-stats']}>
        <div className={styles['run-summary-stat']}>
          <span className={styles['run-summary-value']}>{totalIterations}</span>
          <span className={styles['run-summary-label']}>iterations</span>
        </div>
        <div className={styles['run-summary-stat']}>
          <span className={styles['run-summary-value']}>{totalSteps}</span>
          <span className={styles['run-summary-label']}>steps</span>
        </div>
        <div className={styles['run-summary-stat']}>
          <span className={styles['run-summary-value']}>{diagnostics.llmCalls}</span>
          <span className={styles['run-summary-label']}>LLM</span>
        </div>
        <div className={styles['run-summary-stat']}>
          <span className={styles['run-summary-value']}>{diagnostics.operationCalls}</span>
          <span className={styles['run-summary-label']}>operations</span>
        </div>
        <div className={styles['run-summary-stat']}>
          <span className={styles['run-summary-value']}>{diagnostics.failedOperations}</span>
          <span className={styles['run-summary-label']}>failed</span>
        </div>
      </div>
      {firstError && (
        <div className={styles['run-summary-error']}>
          <strong>{firstError.code}:</strong> {firstError.userMessage}
        </div>
      )}
    </div>
  );
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}


export function AgentRunPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const { data: run, isLoading } = useQuery({
    queryKey: qk.agentRuns.detail(id!),
    queryFn: () => agentRunsApi.get(id!),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: () => agentRunsApi.delete(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agentRuns.all() });
      showSuccess('Запуск удалён');
      navigate('/admin/agent-runs');
    },
    onError: (err: Error) => showError(err.message || 'Ошибка удаления'),
  });

  const handleDeleteConfirm = async () => {
    await deleteMutation.mutateAsync();
  };

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Запуски агентов', href: '/admin/agent-runs' },
    { label: run ? `${run.agent_slug} — ${run.id.substring(0, 8)}` : 'Запуск' },
  ];

  const steps = run?.steps || [];
  const trace = useMemo(() => {
    return buildRunTrace(steps.map((step) => ({
      id: step.id,
      raw_type: step.step_type,
      data: step.data,
      step_number: step.step_number,
      created_at: step.created_at,
      duration_ms: step.duration_ms,
    })));
  }, [steps]);
  const diagnostics = useMemo(() => buildTraceDiagnostics(trace.iterations.flatMap((item) => item.events)), [trace]);
  const orderedEvents = useMemo(
    () =>
      steps.map((step) =>
        normalizeTraceEvent({
          id: step.id,
          raw_type: step.step_type,
          data: step.data,
          step_number: step.step_number,
          created_at: step.created_at,
          duration_ms: step.duration_ms,
        }),
      ),
    [steps],
  );
  const traceTree = useMemo(
    () => buildEntityTree(orderedEvents),
    [orderedEvents],
  );
  const selectedEntity = useMemo(
    () => (selectedEntityId ? findEntityById(traceTree, selectedEntityId) ?? null : null),
    [traceTree, selectedEntityId],
  );
  const inspectorSteps = useMemo<RunStep[]>(
    () =>
      steps.map((step) => ({
        id: step.id,
        type: step.step_type as RunStep['type'],
        data: step.data,
        timestamp: Date.parse(step.created_at) || 0,
      })),
    [steps],
  );
  const OVERVIEW_FIELDS: FieldConfig[] = [
    { key: 'id', type: 'code', label: 'ID', editable: false },
    { key: 'agent_slug', type: 'text', label: 'Агент', editable: false },
    { key: 'status', type: 'badge', label: 'Статус', editable: false },
    { key: 'started_at', type: 'date', label: 'Начат', editable: false },
    { key: 'finished_at', type: 'date', label: 'Завершён', editable: false },
    { key: 'duration_ms', type: 'text', label: 'Длительность', editable: false },
  ];

  const METRICS_FIELDS: FieldConfig[] = [
    { key: 'total_steps', type: 'text', label: 'Шагов', editable: false },
    { key: 'total_tool_calls', type: 'text', label: 'Вызовов инструментов', editable: false },
    { key: 'tokens_in', type: 'text', label: 'Токенов (вход)', editable: false },
    { key: 'tokens_out', type: 'text', label: 'Токенов (выход)', editable: false },
    { key: 'chat_id', type: 'text', label: 'Чат', editable: false },
    { key: 'user_id', type: 'text', label: 'Пользователь', editable: false },
    { key: 'tenant_id', type: 'text', label: 'Тенант', editable: false },
  ];

  const overviewData = useMemo(() => {
    if (!run) return {};
    return {
      id: run.id,
      agent_slug: run.agent_slug,
      status: (
        <Badge tone={getStatusProps('run', run.status).tone as 'info' | 'success' | 'warn' | 'danger' | 'neutral'}>
          {getStatusProps('run', run.status).label}
        </Badge>
      ),
      started_at: formatDate(run.started_at),
      finished_at: formatDate(run.finished_at),
      duration_ms: formatDuration(run.duration_ms),
    };
  }, [run]);

  const metricsData = useMemo(() => {
    if (!run) return {};
    return {
      total_steps: String(run.total_steps),
      total_tool_calls: String(run.total_tool_calls),
      tokens_in: run.tokens_in != null ? String(run.tokens_in) : '—',
      tokens_out: run.tokens_out != null ? String(run.tokens_out) : '—',
      chat_id: run.chat_id ? run.chat_id.substring(0, 8) + '...' : '—',
      user_id: run.user_id ? run.user_id.substring(0, 8) + '...' : '—',
      tenant_id: run.tenant_id.substring(0, 8) + '...',
    };
  }, [run]);

  const snap = run?.context_snapshot;
  const CONTEXT_FIELDS: FieldConfig[] = [
    { key: 'agent_version_id', type: 'code', label: 'Версия агента', editable: false },
    { key: 'execution_mode', type: 'badge', label: 'Режим', editable: false },
    { key: 'model', type: 'text', label: 'Модель', editable: false },
    { key: 'routing_duration_ms', type: 'text', label: 'Роутинг', editable: false },
  ];
  const contextData = useMemo(() => {
    if (!snap) return {};
    return {
      agent_version_id: snap.agent_version_id ?? '—',
      execution_mode: snap.execution_mode ?? '—',
      model: snap.model ?? '—',
      routing_duration_ms: snap.routing_duration_ms != null ? `${snap.routing_duration_ms}ms` : '—',
    };
  }, [snap]);

  const POLICY_FIELDS: FieldConfig[] = [
    { key: 'max_steps', type: 'text', label: 'Max шагов', editable: false },
    { key: 'max_tool_calls', type: 'text', label: 'Max вызовов', editable: false },
    { key: 'max_wall_time_ms', type: 'text', label: 'Макс. время', editable: false },
    { key: 'tool_timeout_ms', type: 'text', label: 'Timeout инструм.', editable: false },
  ];
  const policyData = useMemo(() => {
    const p = snap?.policy;
    if (!p) return {};
    return {
      max_steps: p.max_steps != null ? String(p.max_steps) : '—',
      max_tool_calls: p.max_tool_calls != null ? String(p.max_tool_calls) : '—',
      max_wall_time_ms: p.max_wall_time_ms != null ? `${p.max_wall_time_ms / 1000}s` : '—',
      tool_timeout_ms: p.tool_timeout_ms != null ? `${p.tool_timeout_ms / 1000}s` : '—',
    };
  }, [snap]);

  const availableOperations = useMemo(() => {
    if (!snap?.available_operations || !Array.isArray(snap.available_operations)) return [] as string[];
    const normalized = snap.available_operations
      .map((item) => {
        if (typeof item === 'string') return item.trim();
        if (!item || typeof item !== 'object') return '';
        const record = item as Record<string, unknown>;
        const slug = record.operation_slug ?? record.operation ?? record.tool ?? record.name;
        return typeof slug === 'string' ? slug.trim() : '';
      })
      .filter((item) => item.length > 0);
    return Array.from(new Set(normalized)).sort((a, b) => a.localeCompare(b));
  }, [snap?.available_operations]);

  const snapshotTools = useMemo(() => {
    const direct = Array.isArray(snap?.tools) ? snap.tools.map((item) => item.slug).filter(Boolean) : [];
    return Array.from(new Set([...direct, ...availableOperations])).sort((a, b) => a.localeCompare(b));
  }, [snap?.tools, availableOperations]);

  return (
    <>
      <EntityPageV2
        title={run ? run.agent_slug : 'Запуск агента'}
        mode="view"
        loading={isLoading}
        breadcrumbs={breadcrumbs}
      >
        <Tab
          title="Обзор"
          layout="grid"
          id="overview"
          actions={[
            ...(run?.chat_id
              ? [
                  <Button key="chat-runs" variant="outline" onClick={() => navigate(`/admin/agent-runs?chat_id=${run.chat_id}`)}>
                    Все рансы чата
                  </Button>,
                ]
              : []),
            <Button key="delete" variant="danger" onClick={() => setShowDeleteConfirm(true)}>
              Удалить
            </Button>,
          ]}
        >
          {run && (
            <Block title="Run Summary" icon="activity" iconVariant="primary" width="full">
              <RunSummary run={run} diagnostics={diagnostics} trace={trace} />
            </Block>
          )}

          {snap?.request_text && (
            <Block title="Запрос пользователя" icon="message-square" iconVariant="info" width="full">
              <div className={styles['request-text']}>{snap.request_text}</div>
            </Block>
          )}

          <Block title="Информация" icon="info" iconVariant="info" width="1/2" fields={OVERVIEW_FIELDS} data={overviewData}>
            {run?.error && (
              <div className={styles['error-box']} style={{ marginTop: 12 }}>
                <div className={styles['error-label']}>Ошибка:</div>
                {run.error}
              </div>
            )}
          </Block>

          <Block title="Метрики" icon="activity" iconVariant="primary" width="1/2" fields={METRICS_FIELDS} data={metricsData} />

          {snap && (
            <>
              <Block title="Контекст выполнения" icon="cpu" iconVariant="info" width="1/2" fields={CONTEXT_FIELDS} data={contextData} />
              <Block title="Политика" icon="shield" iconVariant="warning" width="1/2" fields={POLICY_FIELDS} data={policyData} />
            </>
          )}

          {snapshotTools.length > 0 && (
            <Block title="Инструменты" icon="wrench" iconVariant="primary" width="full">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {snapshotTools.map((slug) => (
                  <Badge key={slug} tone="success">
                    {slug}
                  </Badge>
                ))}
              </div>
            </Block>
          )}

          <Block title="Budget Diagnostics" icon="gauge" iconVariant="warning" width="1/2">
            <div className={styles['context-snapshot']}>
              budget events: {diagnostics.budgetEvents}
              {'\n'}last budget: <DiagnosticValue value={diagnostics.lastBudget} />
            </div>
          </Block>

          <Block title="LLM Diagnostics" icon="sparkles" iconVariant="info" width="1/2">
            <div className={styles['context-snapshot']}>
              llm calls: {diagnostics.llmCalls}
              {'\n'}last llm: <DiagnosticValue value={diagnostics.lastLlm} />
            </div>
          </Block>

          <Block title="Operation Diagnostics" icon="wrench" iconVariant="primary" width="full">
            <div className={styles['context-snapshot']}>
              operation events: {diagnostics.operationCalls}
              {'\n'}failed operations: {diagnostics.failedOperations}
              {'\n'}last operation: <DiagnosticValue value={diagnostics.lastOperation} />
            </div>
          </Block>

          {diagnostics.runtimeErrors.length > 0 && (
            <Block title="Runtime Errors" icon="alert-triangle" iconVariant="danger" width="full">
              <div className={styles['context-snapshot']}>
                {diagnostics.runtimeErrors.slice(-3).map((item, idx) => (
                  <div key={`${item.code}-${idx}`} style={{ marginBottom: 10 }}>
                    <div><strong>code:</strong> {item.code}</div>
                    <div><strong>user:</strong> {item.userMessage}</div>
                    <div><strong>operator:</strong> {item.operatorMessage}</div>
                  </div>
                ))}
              </div>
            </Block>
          )}
        </Tab>

        <Tab title="Трейс" layout="full" id="steps" badge={trace.total_events}>
          {trace.total_events > 0 ? (
            <div className={styles['trace-workspace']}>
              <div className={styles['trace-tree-pane']}>
                <TraceTree
                  root={traceTree}
                  selectedId={selectedEntityId}
                  onSelect={(entity: TraceEntity) => setSelectedEntityId(entity.id)}
                  expandedIds={expandedIds}
                  onToggleExpand={(id: string) => {
                    setExpandedIds((prev) => {
                      const next = new Set(prev);
                      if (next.has(id)) next.delete(id);
                      else next.add(id);
                      return next;
                    });
                  }}
                />
              </div>
              <aside className={styles['trace-inspector-pane']}>
                <EntityInspector entity={selectedEntity} steps={inspectorSteps} />
              </aside>
            </div>
          ) : (
            <div className={styles['empty-steps']}>Нет записанных шагов. Возможно, уровень логирования агента — «none».</div>
          )}
        </Tab>
      </EntityPageV2>

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить запуск?"
        message={
          <div>
            <p>
              Вы уверены, что хотите удалить запуск <strong>{run?.agent_slug}</strong>?
            </p>
            <p>Это действие удалит все шаги. Отменить его невозможно.</p>
          </div>
        }
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={handleDeleteConfirm}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}

export default AgentRunPage;
