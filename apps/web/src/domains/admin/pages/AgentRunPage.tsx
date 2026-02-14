/**
 * AgentRunPage - Детальная страница запуска агента
 * 
 * Паттерн: PolicyPage (EntityPageV2 + Tab + ContentBlock + MetaList)
 * Табы: Обзор (grid: инфо + метрики) | Шаги (full: список шагов)
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { agentRunsApi, type AgentRunDetail, type AgentRunStep } from '@/shared/api/agentRuns';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui/EntityPage/EntityPageV2';
import { ContentBlock, Badge, Button } from '@/shared/ui';
import { MetaList } from '@/shared/ui/MetaRow';
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

function StepItem({ step }: { step: AgentRunStep }) {
  const [expanded, setExpanded] = useState(false);
  const dataStr = JSON.stringify(step.data);
  const preview = dataStr.length > 120 ? `${dataStr.substring(0, 120)}...` : dataStr;

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
        <div className={styles['step-preview']}>{preview}</div>
      )}

      {expanded && (
        <pre className={styles['step-data']}>
          {JSON.stringify(step.data, null, 2)}
        </pre>
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

  const overviewMeta = run ? [
    { label: 'ID', value: run.id },
    { label: 'Агент', value: run.agent_slug },
    {
      label: 'Статус',
      value: (
        <Badge tone={getStatusProps('run', run.status).tone as 'info' | 'success' | 'warn' | 'danger' | 'neutral'}>
          {getStatusProps('run', run.status).label}
        </Badge>
      ),
    },
    { label: 'Начат', value: formatDate(run.started_at) },
    { label: 'Завершён', value: formatDate(run.finished_at) },
    { label: 'Длительность', value: formatDuration(run.duration_ms) },
  ] : [];

  const metricsMeta = run ? [
    { label: 'Шагов', value: String(run.total_steps) },
    { label: 'Вызовов инструментов', value: String(run.total_tool_calls) },
    { label: 'Токенов (вход)', value: run.tokens_in != null ? String(run.tokens_in) : '—' },
    { label: 'Токенов (выход)', value: run.tokens_out != null ? String(run.tokens_out) : '—' },
    ...(run.chat_id ? [{ label: 'Чат', value: run.chat_id.substring(0, 8) + '...' }] : []),
    ...(run.user_id ? [{ label: 'Пользователь', value: run.user_id.substring(0, 8) + '...' }] : []),
    { label: 'Тенант', value: run.tenant_id.substring(0, 8) + '...' },
  ] : [];

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
            <Button
              key="delete"
              variant="danger"
              onClick={() => setShowDeleteConfirm(true)}
            >
              Удалить
            </Button>,
          ]}
        >
          <ContentBlock title="Информация" icon="info">
            <MetaList items={overviewMeta} />
            {run?.error && (
              <div className={styles['error-box']} style={{ marginTop: 12 }}>
                <div className={styles['error-label']}>Ошибка:</div>
                {run.error}
              </div>
            )}
          </ContentBlock>

          <ContentBlock title="Метрики" icon="activity">
            <MetaList items={metricsMeta} />
          </ContentBlock>
        </Tab>

        <Tab
          title="Шаги"
          layout="full"
          id="steps"
          badge={steps.length}
        >
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
