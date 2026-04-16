/**
 * AgentRunPage - Детальная страница запуска агента
 * 
 * Паттерн: PolicyPage (EntityPageV2 + Tab + ContentBlock + MetaList)
 * Табы: Обзор (grid: инфо + метрики) | Шаги (full: список шагов)
 */
import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { agentRunsApi, type AgentRunDetail, type AgentRunStep } from '@/shared/api/agentRuns';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { Badge, Button } from '@/shared/ui';
import { getStatusProps } from '@/shared/lib/statusConfig';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
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

const STEP_TYPE_LABELS: Record<string, string> = {
  user_request: 'Запрос',
  routing: 'Маршрутизация',
  llm_request: 'LLM запрос',
  llm_response: 'LLM ответ',
  tool_call: 'Вызов инструмента',
  tool_result: 'Результат инструмента',
  final_response: 'Финальный ответ',
  error: 'Ошибка',
};

const STEP_TYPE_TONES: Record<string, 'info' | 'success' | 'warn' | 'danger' | 'neutral'> = {
  user_request: 'neutral',
  routing: 'info',
  llm_request: 'info',
  llm_response: 'info',
  tool_call: 'warn',
  tool_result: 'success',
  final_response: 'success',
  error: 'danger',
};

type StepPreviewItem = {
  label: string;
  value: string;
  source: 'preview' | 'raw';
};

function toPreviewString(value: unknown, maxLen = 220): string {
  if (value == null) return '—';
  if (typeof value === 'string') {
    return value.length > maxLen ? `${value.slice(0, maxLen)}...` : value;
  }

  const raw = JSON.stringify(value);
  return raw.length > maxLen ? `${raw.slice(0, maxLen)}...` : raw;
}

function buildStepPreview(step: AgentRunStep): StepPreviewItem[] {
  const data = step.data;
  const items: StepPreviewItem[] = [];

  if (step.step_type === 'tool_call') {
    const hasPreview = data.arguments_preview != null;
    const argsPreview = hasPreview ? data.arguments_preview : data.arguments;
    items.push({
      label: 'Аргументы',
      value: toPreviewString(argsPreview),
      source: hasPreview ? 'preview' : 'raw',
    });
    return items;
  }

  if (step.step_type === 'tool_result') {
    const hasPreview = data.result_preview != null;
    const resultPreview = hasPreview ? data.result_preview : data.result;
    items.push({
      label: 'Результат',
      value: toPreviewString(resultPreview),
      source: hasPreview ? 'preview' : 'raw',
    });
    return items;
  }

  if (step.step_type === 'llm_response') {
    items.push({
      label: 'Ответ LLM',
      value: toPreviewString(data.content),
      source: 'raw',
    });
    return items;
  }

  if (step.step_type === 'final_response') {
    items.push({
      label: 'Финал',
      value: toPreviewString(data.content),
      source: 'raw',
    });
    return items;
  }

  items.push({
    label: 'Данные',
    value: toPreviewString(data),
    source: 'raw',
  });
  return items;
}

function StepItem({ step }: { step: AgentRunStep }) {
  const [expanded, setExpanded] = useState(false);
  const previewItems = buildStepPreview(step);

  return (
    <div
      className={styles['step-item']}
      onClick={() => setExpanded(!expanded)}
    >
      <div className={styles['step-header']}>
        <span className={styles['step-number']}>#{step.step_number + 1}</span>
        <Badge
          tone={STEP_TYPE_TONES[step.step_type] || 'neutral'}
        >
          {STEP_TYPE_LABELS[step.step_type] || step.step_type}
        </Badge>
        <div className={styles['step-meta']}>
          {step.tokens_in != null && (
            <span>in: {step.tokens_in}</span>
          )}
          {step.tokens_out != null && (
            <span>out: {step.tokens_out}</span>
          )}
          {step.duration_ms != null && (
            <span>{step.duration_ms}ms</span>
          )}
          <span className={styles['step-toggle']}>{expanded ? '▼' : '▶'}</span>
        </div>
      </div>

      {!expanded && (
        <div className={styles['step-preview']}>
          {previewItems.map((item) => (
            <div key={item.label} className={styles['step-preview-row']}>
              <span className={styles['step-preview-label']}>{item.label}:</span>{' '}
              <span
                className={`${styles['step-preview-source']} ${styles[`step-preview-source-${item.source}`]}`}
              >
                {item.source}
              </span>{' '}
              <span className={styles['step-preview-value']}>{item.value}</span>
            </div>
          ))}
        </div>
      )}

      {expanded && (
        <>
          <div className={styles['step-preview-expanded']}>
            {previewItems.map((item) => (
              <div key={item.label} className={styles['step-preview-row']}>
                <span className={styles['step-preview-label']}>{item.label}:</span>{' '}
                <span
                  className={`${styles['step-preview-source']} ${styles[`step-preview-source-${item.source}`]}`}
                >
                  {item.source}
                </span>{' '}
                <span className={styles['step-preview-value']}>{item.value}</span>
              </div>
            ))}
          </div>
          <pre className={styles['step-data']}>
            {JSON.stringify(step.data, null, 2)}
          </pre>
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

/* ─── Field configs ─── */

const OVERVIEW_FIELDS: FieldConfig[] = [
  {
    key: 'id',
    type: 'code',
    label: 'ID',
    editable: false,
  },
  {
    key: 'agent_slug',
    type: 'text',
    label: 'Агент',
    editable: false,
  },
  {
    key: 'status',
    type: 'badge',
    label: 'Статус',
    editable: false,
  },
  {
    key: 'started_at',
    type: 'date',
    label: 'Начат',
    editable: false,
  },
  {
    key: 'finished_at',
    type: 'date',
    label: 'Завершён',
    editable: false,
  },
  {
    key: 'duration_ms',
    type: 'text',
    label: 'Длительность',
    editable: false,
  },
];

const METRICS_FIELDS: FieldConfig[] = [
  {
    key: 'total_steps',
    type: 'text',
    label: 'Шагов',
    editable: false,
  },
  {
    key: 'total_tool_calls',
    type: 'text',
    label: 'Вызовов инструментов',
    editable: false,
  },
  {
    key: 'tokens_in',
    type: 'text',
    label: 'Токенов (вход)',
    editable: false,
  },
  {
    key: 'tokens_out',
    type: 'text',
    label: 'Токенов (выход)',
    editable: false,
  },
  {
    key: 'chat_id',
    type: 'text',
    label: 'Чат',
    editable: false,
  },
  {
    key: 'user_id',
    type: 'text',
    label: 'Пользователь',
    editable: false,
  },
  {
    key: 'tenant_id',
    type: 'text',
    label: 'Тенант',
    editable: false,
  },
];

// ─── Data for blocks ───
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
                  <Button
                    key="chat-runs"
                    variant="outline"
                    onClick={() => navigate(`/admin/agent-runs?chat_id=${run.chat_id}`)}
                  >
                    Все рансы чата
                  </Button>,
                ]
              : []),
            <Button key="delete" variant="danger" onClick={() => setShowDeleteConfirm(true)}>
              Удалить
            </Button>,
          ]}
        >
          {/* Request text — full width if present */}
          {snap?.request_text && (
            <Block title="Запрос пользователя" icon="message-square" iconVariant="info" width="full">
              <div className={styles['request-text']}>{snap.request_text}</div>
            </Block>
          )}

          {/* Row: Information + Metrics */}
          <Block
            title="Информация"
            icon="info"
            iconVariant="info"
            width="1/2"
            fields={OVERVIEW_FIELDS}
            data={overviewData}
          >
            {run?.error && (
              <div className={styles['error-box']} style={{ marginTop: 12 }}>
                <div className={styles['error-label']}>Ошибка:</div>
                {run.error}
              </div>
            )}
          </Block>

          <Block
            title="Метрики"
            icon="activity"
            iconVariant="primary"
            width="1/2"
            fields={METRICS_FIELDS}
            data={metricsData}
          />

          {/* Row: Context + Policy (only if context_snapshot exists) */}
          {snap && (
            <>
              <Block
                title="Контекст выполнения"
                icon="cpu"
                iconVariant="info"
                width="1/2"
                fields={CONTEXT_FIELDS}
                data={contextData}
              />
              <Block
                title="Политика"
                icon="shield"
                iconVariant="warning"
                width="1/2"
                fields={POLICY_FIELDS}
                data={policyData}
              />
            </>
          )}

          {/* Tools used */}
          {snap?.tools && snap.tools.length > 0 && (
            <Block title="Инструменты" icon="wrench" iconVariant="primary" width="full">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {snap.tools.map(t => (
                  <Badge key={t.slug} tone={t.has_credentials ? 'success' : 'warn'}>
                    {t.slug}
                  </Badge>
                ))}
              </div>
            </Block>
          )}
        </Tab>

        <Tab title="Шаги" layout="full" id="steps" badge={steps.length}>
          {steps.length > 0 ? (
            <div className={styles['steps-list']}>
              {steps.map((step) => (
                <StepItem key={step.id} step={step} />
              ))}
            </div>
          ) : (
            <div className={styles['empty-steps']}>
              Нет записанных шагов. Возможно, уровень логирования агента — «none».
            </div>
          )}
        </Tab>
      </EntityPageV2>

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить запуск?"
        message={
          <div>
            <p>Вы уверены, что хотите удалить запуск <strong>{run?.agent_slug}</strong>?</p>
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
