/**
 * AgentRunsPage - Логи запусков агентов
 * 
 * Единый стиль с остальными админ-реестрами.
 */
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentRunsApi, AgentRun, AgentRunDetail, AgentRunFilter } from '@/shared/api';
import { AdminPage } from '@/shared/ui';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Modal from '@/shared/ui/Modal';
import { Skeleton } from '@/shared/ui/Skeleton';
import { ActionsButton, type ActionItem } from '@/shared/ui/ActionsButton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './RegistryPage.module.css';

function formatDuration(ms?: number): string {
  if (!ms) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const STATUS_TONES: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
  running: 'info',
  completed: 'success',
  failed: 'danger',
};

const STEP_ICONS: Record<string, string> = {
  llm_request: '🤖',
  tool_call: '🔧',
  tool_result: '📤',
  final_response: '✅',
};

const STEP_TONES: Record<string, 'info' | 'success' | 'warning' | 'neutral'> = {
  llm_request: 'info',
  tool_call: 'warning',
  tool_result: 'success',
  final_response: 'success',
};

function StepItem({ step }: { step: AgentRunDetail['steps'][0] }) {
  const [expanded, setExpanded] = useState(false);
  const dataPreview = JSON.stringify(step.data).slice(0, 100);

  return (
    <div 
      style={{ 
        padding: '12px', 
        background: 'var(--bg-subtle)', 
        borderRadius: 'var(--radius-sm)',
        marginBottom: '8px',
      }}
    >
      <div 
        onClick={() => setExpanded(!expanded)}
        style={{ 
          cursor: 'pointer', 
          display: 'flex', 
          alignItems: 'center', 
          gap: '8px',
        }}
      >
        <span>{STEP_ICONS[step.step_type] || '📝'}</span>
        <Badge tone={STEP_TONES[step.step_type] || 'neutral'} size="small">
          #{step.step_number + 1} {step.step_type.replace(/_/g, ' ')}
        </Badge>
        {step.duration_ms && (
          <span style={{ color: 'var(--muted)', fontSize: '12px' }}>
            {step.duration_ms}ms
          </span>
        )}
        <span style={{ marginLeft: 'auto' }}>{expanded ? '▼' : '▶'}</span>
      </div>
      {!expanded && (
        <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '4px' }}>
          {dataPreview}{dataPreview.length >= 100 ? '...' : ''}
        </div>
      )}
      {expanded && (
        <pre style={{
          marginTop: '8px',
          padding: '12px',
          background: 'var(--bg-hover)',
          borderRadius: 'var(--radius-sm)',
          fontSize: '12px',
          overflow: 'auto',
          maxHeight: '200px',
        }}>
          {JSON.stringify(step.data, null, 2)}
        </pre>
      )}
    </div>
  );
}

function RunDetailModal({ 
  run, 
  onClose 
}: { 
  run: AgentRunDetail; 
  onClose: () => void;
}) {
  return (
    <Modal open={!!run} onClose={onClose} title={`Запуск: ${run.agent_slug}`}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(3, 1fr)', 
          gap: '12px',
        }}>
          <div>
            <strong>Статус:</strong>{' '}
            <Badge tone={STATUS_TONES[run.status] || 'neutral'}>{run.status}</Badge>
          </div>
          <div>
            <strong>Длительность:</strong> {formatDuration(run.duration_ms)}
          </div>
          <div>
            <strong>Шагов:</strong> {run.total_steps}
          </div>
          <div>
            <strong>Tool Calls:</strong> {run.total_tool_calls}
          </div>
          <div>
            <strong>Начат:</strong> {formatDate(run.started_at)}
          </div>
        </div>
        
        {run.error && (
          <div style={{ 
            padding: '12px', 
            background: 'var(--danger-bg)', 
            borderRadius: 'var(--radius-sm)',
            color: 'var(--danger)',
          }}>
            <strong>Ошибка:</strong> {run.error}
          </div>
        )}

        <div>
          <h4 style={{ margin: '0 0 12px' }}>Шаги ({run.steps?.length || 0})</h4>
          <div style={{ maxHeight: '400px', overflow: 'auto' }}>
            {run.steps?.length ? (
              run.steps.map((step) => (
                <StepItem key={step.id} step={step} />
              ))
            ) : (
              <div style={{ color: 'var(--muted)' }}>Нет записанных шагов</div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button variant="outline" onClick={onClose}>Закрыть</Button>
        </div>
      </div>
    </Modal>
  );
}

export function AgentRunsPage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [filters, setFilters] = useState<AgentRunFilter>({
    page: 1,
    page_size: 20,
  });
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const { data: runsData, isLoading } = useQuery({
    queryKey: ['agent-runs', filters],
    queryFn: () => agentRunsApi.list(filters),
  });

  const { data: selectedRun, isLoading: isLoadingDetail } = useQuery({
    queryKey: ['agent-runs', selectedRunId],
    queryFn: () => agentRunsApi.get(selectedRunId!),
    enabled: !!selectedRunId,
  });

  const { data: stats } = useQuery({
    queryKey: ['agent-runs', 'stats'],
    queryFn: () => agentRunsApi.getStats(),
  });

  const deleteMutation = useMutation({
    mutationFn: (runId: string) => agentRunsApi.delete(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent-runs'] });
      showSuccess('Run deleted');
    },
    onError: () => showError('Failed to delete run'),
  });

  const deleteOldMutation = useMutation({
    mutationFn: (beforeDate: string) => agentRunsApi.deleteOld(beforeDate),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['agent-runs'] });
      showSuccess(`Deleted ${data.deleted_count} runs`);
    },
    onError: () => showError('Failed to delete old runs'),
  });

  const handleDeleteOld = () => {
    const days = prompt('Delete runs older than N days:', '30');
    if (!days) return;
    
    const daysNum = parseInt(days, 10);
    if (isNaN(daysNum) || daysNum < 1) {
      showError('Invalid number of days');
      return;
    }

    const beforeDate = new Date();
    beforeDate.setDate(beforeDate.getDate() - daysNum);
    
    if (confirm(`Delete all runs before ${beforeDate.toLocaleDateString()}?`)) {
      deleteOldMutation.mutate(beforeDate.toISOString());
    }
  };

  const handleDelete = (e: React.MouseEvent, runId: string) => {
    e.stopPropagation();
    if (confirm('Delete this run?')) {
      deleteMutation.mutate(runId);
    }
  };

  const totalPages = runsData ? Math.ceil(runsData.total / runsData.page_size) : 0;

  const getActions = (run: AgentRun): ActionItem[] => [
    {
      label: 'Подробнее',
      onClick: () => setSelectedRunId(run.id),
    },
    {
      label: 'Удалить',
      onClick: () => {
        if (confirm('Удалить этот запуск?')) {
          deleteMutation.mutate(run.id);
        }
      },
      variant: 'danger',
    },
  ];

  return (
    <AdminPage
      title="Запуски агентов"
      subtitle="Логи выполнения агентов и их шагов"
      actions={[
        {
          label: 'Очистить старые',
          onClick: handleDeleteOld,
          variant: 'outline',
        },
      ]}
    >
      {/* Stats */}
      {stats && (
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(4, 1fr)', 
          gap: '16px', 
          marginBottom: '24px',
        }}>
          <div style={{ padding: '16px', background: 'var(--bg-subtle)', borderRadius: 'var(--radius)' }}>
            <div style={{ fontSize: '12px', color: 'var(--muted)' }}>Всего</div>
            <div style={{ fontSize: '24px', fontWeight: 600 }}>{stats.total_runs}</div>
          </div>
          <div style={{ padding: '16px', background: 'var(--bg-subtle)', borderRadius: 'var(--radius)' }}>
            <div style={{ fontSize: '12px', color: 'var(--muted)' }}>Завершено</div>
            <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--success)' }}>
              {stats.by_status.completed || 0}
            </div>
          </div>
          <div style={{ padding: '16px', background: 'var(--bg-subtle)', borderRadius: 'var(--radius)' }}>
            <div style={{ fontSize: '12px', color: 'var(--muted)' }}>Ошибки</div>
            <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--danger)' }}>
              {stats.by_status.failed || 0}
            </div>
          </div>
          <div style={{ padding: '16px', background: 'var(--bg-subtle)', borderRadius: 'var(--radius)' }}>
            <div style={{ fontSize: '12px', color: 'var(--muted)' }}>Среднее время</div>
            <div style={{ fontSize: '24px', fontWeight: 600 }}>{formatDuration(stats.avg_duration_ms)}</div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>АГЕНТ</th>
              <th>СТАТУС</th>
              <th>ШАГИ</th>
              <th>TOOL CALLS</th>
              <th>ВРЕМЯ</th>
              <th>НАЧАТ</th>
              <th>ДЕЙСТВИЯ</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <tr key={i}>
                  {Array.from({ length: 7 }).map((__, j) => (
                    <td key={j}>
                      <Skeleton width={j === 0 ? 120 : 80} />
                    </td>
                  ))}
                </tr>
              ))
            ) : !runsData?.items.length ? (
              <tr>
                <td colSpan={7} className={styles.emptyState}>
                  Запуски не найдены. Они появятся после выполнения агентов.
                </td>
              </tr>
            ) : (
              runsData.items.map((run) => (
                <tr key={run.id} onClick={() => setSelectedRunId(run.id)} style={{ cursor: 'pointer' }}>
                  <td>
                    <code className={styles.code}>{run.agent_slug}</code>
                  </td>
                  <td>
                    <Badge tone={STATUS_TONES[run.status] || 'neutral'} size="small">
                      {run.status}
                    </Badge>
                  </td>
                  <td>{run.total_steps}</td>
                  <td>{run.total_tool_calls}</td>
                  <td>
                    <span className={styles.muted}>{formatDuration(run.duration_ms)}</span>
                  </td>
                  <td>
                    <span className={styles.muted}>{formatDate(run.started_at)}</span>
                  </td>
                  <td>
                    <ActionsButton actions={getActions(run)} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '16px', marginTop: '16px' }}>
          <Button
            variant="outline"
            size="small"
            disabled={filters.page === 1}
            onClick={() => setFilters({ ...filters, page: (filters.page || 1) - 1 })}
          >
            Назад
          </Button>
          <span style={{ color: 'var(--muted)' }}>
            Страница {filters.page} из {totalPages}
          </span>
          <Button
            variant="outline"
            size="small"
            disabled={filters.page === totalPages}
            onClick={() => setFilters({ ...filters, page: (filters.page || 1) + 1 })}
          >
            Вперёд
          </Button>
        </div>
      )}

      {/* Detail Modal */}
      {selectedRunId && selectedRun && !isLoadingDetail && (
        <RunDetailModal
          run={selectedRun}
          onClose={() => setSelectedRunId(null)}
        />
      )}
    </AdminPage>
  );
}
