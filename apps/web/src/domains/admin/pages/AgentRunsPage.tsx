/**
 * AgentRunsPage - Логи запусков агентов
 * 
 * Единый стиль с остальными админ-реестрами.
 */
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentRunsApi, AgentRun, AgentRunDetail, AgentRunFilter } from '@/shared/api';
import { AdminPage, DataTable, type DataTableColumn, Badge, Button, Modal, ActionsButton, type ActionItem } from '@/shared/ui';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { getStatusProps } from '@/shared/lib/statusConfig';

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
            <Badge tone={getStatusProps('run', run.status).tone}>{getStatusProps('run', run.status).label}</Badge>
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

  const columns: DataTableColumn<AgentRun>[] = [
    {
      key: 'agent_slug',
      label: 'АГЕНТ',
      render: (run) => (
        <code style={{ 
          fontFamily: 'var(--font-mono, monospace)', 
          fontSize: '0.75rem',
          background: 'var(--bg-subtle)',
          padding: '2px 6px',
          borderRadius: '4px',
        }}>
          {run.agent_slug}
        </code>
      ),
    },
    {
      key: 'status',
      label: 'СТАТУС',
      width: 100,
      render: (run) => (
        <Badge tone={getStatusProps('run', run.status).tone} size="small">
          {getStatusProps('run', run.status).label}
        </Badge>
      ),
    },
    {
      key: 'total_steps',
      label: 'ШАГИ',
      width: 80,
    },
    {
      key: 'total_tool_calls',
      label: 'TOOL CALLS',
      width: 100,
    },
    {
      key: 'duration_ms',
      label: 'ВРЕМЯ',
      width: 100,
      render: (run) => (
        <span style={{ color: 'var(--muted)' }}>{formatDuration(run.duration_ms)}</span>
      ),
    },
    {
      key: 'started_at',
      label: 'НАЧАТ',
      width: 150,
      render: (run) => (
        <span style={{ color: 'var(--muted)' }}>{formatDate(run.started_at)}</span>
      ),
    },
    {
      key: 'actions',
      label: '',
      width: 50,
      render: (run) => <ActionsButton actions={getActions(run)} />,
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
      <DataTable
        columns={columns}
        data={runsData?.items || []}
        keyField="id"
        loading={isLoading}
        emptyText="Запуски не найдены. Они появятся после выполнения агентов."
        onRowClick={(run) => setSelectedRunId(run.id)}
        paginated
        pageSize={filters.page_size}
        currentPage={filters.page}
        totalItems={runsData?.total}
        onPageChange={(page) => setFilters({ ...filters, page })}
      />

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
