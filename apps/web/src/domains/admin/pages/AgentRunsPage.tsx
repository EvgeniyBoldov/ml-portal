import { useNavigate } from 'react-router-dom';
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

export default function AgentRunsPage() {
  const navigate = useNavigate();
  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['admin', 'agent-runs'], queryFn: agentRunsApi.list, staleTime: 15_000,
  });
  const { data: memoryJobs = [], isLoading: memoryLoading } = useQuery({
    queryKey: ['admin', 'memory-jobs'], queryFn: memoryJobsApi.list, staleTime: 5_000, refetchInterval: 5_000,
  });
  const columns: DataTableColumn<AgentRunListItem>[] = [
    { key: 'agent_slug', label: 'АГЕНТ', sortable: true, render: (run) => <><strong>{run.agent_name || run.agent_slug || 'agent'}</strong><small style={{ display: 'block', color: 'var(--text-secondary)' }}>{run.agent_slug}</small></> },
    { key: 'task_title', label: 'ЗАДАЧА', render: (run) => <span>{run.task_title || 'Без названия задачи'}</span> },
    { key: 'logging_level', label: 'ЛОГИРОВАНИЕ', width: 150, render: (run) => <Badge tone="neutral">{loggingLevelLabel[run.logging_level] || run.logging_level}</Badge> },
    { key: 'started_at', label: 'ЗАПУЩЕН', sortable: true, width: 190, render: (run) => <span style={{ color: 'var(--text-secondary)' }}>{formatDate(run.started_at)}</span> },
    { key: 'tenant_id', label: 'ТЕНАНТ', width: 130, render: (run) => <code>{run.tenant_id ? run.tenant_id.slice(0, 8) : '—'}</code> },
  ];
  const memoryColumns: DataTableColumn<MemoryJobListItem>[] = [
    { key: 'document_title', label: 'ДОКУМЕНТ', sortable: true, render: (job) => <><strong>{job.document_title || job.document_filename || 'Документ без названия'}</strong><small style={{ display: 'block', color: 'var(--text-secondary)' }}>{job.document_filename}</small></> },
    { key: 'status', label: 'СТАТУС', width: 170, render: (job) => <Badge tone={job.status === 'failed' ? 'danger' : job.status === 'approved' || job.status === 'awaiting_review' ? 'success' : 'neutral'}>{job.status}</Badge> },
    { key: 'candidate_count', label: 'КАНДИДАТЫ', width: 120, render: (job) => <span>{job.candidate_count}</span> },
    { key: 'updated_at', label: 'ОБНОВЛЁН', sortable: true, width: 190, render: (job) => <span style={{ color: 'var(--text-secondary)' }}>{formatDate(job.updated_at)}</span> },
    { key: 'visibility_tenant_id', label: 'ТЕНАНТ', width: 130, render: (job) => <code>{job.visibility_tenant_id ? job.visibility_tenant_id.slice(0, 8) : 'Общий'}</code> },
  ];
  return (
    <EntityPageV2 title="Запуски агентов" mode="view" breadcrumbs={[{ label: 'Запуски агентов' }]}>
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
