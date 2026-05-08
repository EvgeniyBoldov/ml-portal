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
import { buildRunTrace } from '@/domains/runtimeTrace/normalize';
import type { SemanticEvent } from '@/domains/runtimeTrace/types';
import { buildTraceDiagnostics } from '@/domains/runtimeTrace/components/TraceDiagnosticsSummary';
import styles from './AgentRunPage.module.css';

function formatDuration(ms?: number): string {
  if (!ms) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
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

function eventTone(status: SemanticEvent['status']): 'info' | 'success' | 'warn' | 'danger' | 'neutral' {
  if (status === 'ok') return 'success';
  if (status === 'warn') return 'warn';
  if (status === 'error') return 'danger';
  return 'info';
}

function StepItem({ event, index }: { event: SemanticEvent; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={styles['step-item']} onClick={() => setExpanded((v) => !v)}>
      <div className={styles['step-header']}>
        <span className={styles['step-number']}>#{index + 1}</span>
        <Badge tone={eventTone(event.status)}>{event.title}</Badge>
        <Badge tone="neutral">{event.category}</Badge>
        <div className={styles['step-meta']}>
          {event.duration_ms != null && <span>{event.duration_ms}ms</span>}
          <span className={styles['step-toggle']}>{expanded ? '▼' : '▶'}</span>
        </div>
      </div>

      <div className={styles['step-preview']}>
        <div className={styles['step-preview-row']}>
          <span className={styles['step-preview-label']}>Summary:</span>
          <span className={styles['step-preview-value']}>{event.summary || '—'}</span>
        </div>
      </div>

      {expanded && (
        <>
          <div className={styles['step-preview-expanded']}>
            <div className={styles['step-preview-row']}>
              <span className={styles['step-preview-label']}>Phase:</span>
              <span className={styles['step-preview-value']}>{event.phase}</span>
            </div>
            {event.started_at && (
              <div className={styles['step-preview-row']}>
                <span className={styles['step-preview-label']}>At:</span>
                <span className={styles['step-preview-value']}>{formatDate(event.started_at)}</span>
              </div>
            )}
          </div>
          <pre className={styles['step-data']}>{JSON.stringify(event.raw.raw, null, 2)}</pre>
        </>
      )}
    </div>
  );
}

export function AgentRunPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

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
    if (run?.trace) return run.trace;
    return buildRunTrace(steps.map((step) => ({
      id: step.id,
      raw_type: step.step_type,
      data: step.data,
      step_number: step.step_number,
      created_at: step.created_at,
      duration_ms: step.duration_ms,
    })));
  }, [run?.trace, steps]);
  const diagnostics = useMemo(() => buildTraceDiagnostics(trace.iterations.flatMap((item) => item.events)), [trace]);

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

          {snap?.tools && snap.tools.length > 0 && (
            <Block title="Инструменты" icon="wrench" iconVariant="primary" width="full">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {snap.tools.map((t) => (
                  <Badge key={t.slug} tone={t.has_credentials ? 'success' : 'warn'}>
                    {t.slug}
                  </Badge>
                ))}
              </div>
            </Block>
          )}

          <Block title="Budget Diagnostics" icon="gauge" iconVariant="warning" width="1/2">
            <div className={styles['context-snapshot']}>
              budget events: {diagnostics.budgetEvents}
              {'\n'}last budget: {diagnostics.lastBudget}
            </div>
          </Block>

          <Block title="LLM Diagnostics" icon="sparkles" iconVariant="info" width="1/2">
            <div className={styles['context-snapshot']}>
              llm calls: {diagnostics.llmCalls}
              {'\n'}last llm: {diagnostics.lastLlm}
            </div>
          </Block>

          <Block title="Operation Diagnostics" icon="wrench" iconVariant="primary" width="full">
            <div className={styles['context-snapshot']}>
              operation events: {diagnostics.operationCalls}
              {'\n'}failed operations: {diagnostics.failedOperations}
              {'\n'}last operation: {diagnostics.lastOperation}
            </div>
          </Block>
        </Tab>

        <Tab title="Трейс" layout="full" id="steps" badge={trace.total_events}>
          {trace.iterations.length > 0 ? (
            <div className={styles['steps-list']}>
              {trace.iterations.map((iteration) => (
                <div key={iteration.index}>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', margin: '12px 0 6px' }}>
                    Итерация #{iteration.index + 1}
                  </div>
                  {iteration.events.map((event, idx) => (
                    <StepItem key={event.id} event={event} index={idx} />
                  ))}
                </div>
              ))}
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
