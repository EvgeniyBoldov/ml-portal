import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { agentRunsApi, memoryJobsApi, type AgentRunListItem, type MemoryJobListItem } from '@/shared/api/admin';
import { DataTable, type DataTableColumn, Badge } from '@/shared/ui';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';

const formatDate = (value: string): string => new Date(value).toLocaleString('ru-RU');
const loggingLevelLabel: Record<string, string> = {
  error: 'Только ошибки',
  errors: 'Только ошибки',
  brief: 'Краткий',
  full: 'Полный',
  none: 'Выключено',
};
const runStatusLabel: Record<string, string> = {
  completed: 'Завершён',
  failed: 'Ошибка',
  cancelled: 'Отменён',
  running: 'Выполняется',
  queued: 'В очереди',
  waiting_retry: 'Повтор',
  waiting_input: 'Ожидает ответа',
  paused: 'На паузе',
  unfulfillable: 'Не выполнено',
};
const runStatusTone = (status: string): 'neutral' | 'success' | 'warn' | 'danger' | 'info' => {
  if (status === 'completed') return 'success';
  if (status === 'failed' || status === 'unfulfillable') return 'danger';
  if (status === 'cancelled' || status === 'waiting_retry' || status === 'waiting_input' || status === 'paused') return 'warn';
  if (status === 'running') return 'info';
  return 'neutral';
};

export default function AgentRunsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') === 'memory' ? 'memory' : 'agents';
  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['admin', 'agent-runs'], queryFn: agentRunsApi.list, staleTime: 15_000,
  });
  const { data: memoryJobs = [], isLoading: memoryLoading } = useQuery({
    queryKey: ['admin', 'memory-jobs'], queryFn: memoryJobsApi.list, staleTime: 5_000, refetchInterval: 5_000,
  });
  const columns: DataTableColumn<AgentRunListItem>[] = [
    { key: 'agent_slug', label: 'АГЕНТ', sortable: true, width: 180, render: (run) => <><strong title={run.agent_name || run.agent_slug || 'agent'}>{run.agent_name || run.agent_slug || 'agent'}</strong><small style={{ display: 'block', color: 'var(--text-secondary)' }}>{run.agent_slug}</small></> },
    {
      key: 'agent_type', label: 'ТИП', width: 120,
      render: (run) => <Badge tone={run.agent_type === 'shadow' ? 'info' : 'neutral'}>{run.agent_type === 'shadow' ? 'Теневой' : 'Обычный'}</Badge>,
    },
    {
      key: 'status', label: 'СТАТУС', width: 150,
      render: (run) => <Badge tone={runStatusTone(run.status)}>{runStatusLabel[run.status] || run.status}</Badge>,
    },
    {
      key: 'task_title', label: 'ЗАДАЧА', width: 540,
      render: (run) => <span title={run.task_title || undefined}>
        {run.task_title ? `${run.task_title.slice(0, 180)}${run.task_title.length > 180 ? '…' : ''}` : 'Задача не записана'}
      </span>,
    },
    { key: 'logging_level', label: 'ЛОГИРОВАНИЕ', width: 150, render: (run) => <Badge tone="neutral">{loggingLevelLabel[run.logging_level] || run.logging_level}</Badge> },
    { key: 'started_at', label: 'ЗАПУЩЕН', sortable: true, width: 190, render: (run) => <span style={{ color: 'var(--text-secondary)' }}>{formatDate(run.started_at)}</span> },
    { key: 'user_name', label: 'ПОЛЬЗОВАТЕЛЬ', width: 180, render: (run) => <span title={run.user_name || undefined}>{run.user_name || '—'}</span> },
  ];
  const memoryColumns: DataTableColumn<MemoryJobListItem>[] = [
    { key: 'document_title', label: 'ДОКУМЕНТ', sortable: true, render: (job) => <><strong>{job.document_title || job.document_filename || 'Документ без названия'}</strong><small style={{ display: 'block', color: 'var(--text-secondary)' }}>{job.document_filename}</small></> },
    { key: 'status', label: 'СТАТУС', width: 170, render: (job) => <Badge tone={job.status === 'failed' ? 'danger' : job.status === 'approved' || job.status === 'awaiting_review' ? 'success' : 'neutral'}>{job.status}</Badge> },
    { key: 'candidate_count', label: 'КАНДИДАТЫ', width: 120, render: (job) => <span>{job.candidate_count}</span> },
    { key: 'updated_at', label: 'ОБНОВЛЁН', sortable: true, width: 190, render: (job) => <span style={{ color: 'var(--text-secondary)' }}>{formatDate(job.updated_at)}</span> },
    { key: 'visibility_tenant_id', label: 'ТЕНАНТ', width: 130, render: (job) => <code>{job.visibility_tenant_id ? job.visibility_tenant_id.slice(0, 8) : 'Общий'}</code> },
  ];
  return (
    <EntityPageV2 title="Запуски агентов" mode="view" defaultTab={activeTab} onTabChange={(tab) => {
      setSearchParams((current) => {
        const next = new URLSearchParams(current);
        next.set('tab', tab);
        return next;
      }, { replace: true });
    }} breadcrumbs={[{ label: 'Запуски агентов' }]}>
      <Tab title="Агенты" id="agents" layout="full" badge={runs.length}>
        <DataTable columns={columns} data={runs} keyField="agent_execution_id" loading={isLoading}
          emptyText="Нет запусков с включённым логированием." paginated pageSize={20}
          onRowClick={(run) => navigate(`/admin/agent-runs/${run.agent_execution_id}`)} />
      </Tab>
      <Tab title="Мемори" id="memory" layout="full" badge={memoryJobs.length}>
        <DataTable columns={memoryColumns} data={memoryJobs} keyField="id" loading={memoryLoading}
          emptyText="Задач извлечения памяти пока нет." paginated pageSize={20}
          onRowClick={(job) => navigate(`/admin/agent-runs/memory/${job.id}`)} />
      </Tab>
    </EntityPageV2>
  );
}
