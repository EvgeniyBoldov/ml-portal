import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { agentRunsApi, type AgentRunListItem } from '@/shared/api/admin';
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
  const columns: DataTableColumn<AgentRunListItem>[] = [
    { key: 'agent_slug', label: 'АГЕНТ', sortable: true, render: (run) => <><strong>{run.agent_name || run.agent_slug || 'agent'}</strong><small style={{ display: 'block', color: 'var(--text-secondary)' }}>{run.agent_slug}</small></> },
    { key: 'task_title', label: 'ЗАДАЧА', render: (run) => <span>{run.task_title || 'Без названия задачи'}</span> },
    { key: 'logging_level', label: 'ЛОГИРОВАНИЕ', width: 150, render: (run) => <Badge tone="neutral">{loggingLevelLabel[run.logging_level] || run.logging_level}</Badge> },
    { key: 'started_at', label: 'ЗАПУЩЕН', sortable: true, width: 190, render: (run) => <span style={{ color: 'var(--text-secondary)' }}>{formatDate(run.started_at)}</span> },
    { key: 'tenant_id', label: 'ТЕНАНТ', width: 130, render: (run) => <code>{run.tenant_id ? run.tenant_id.slice(0, 8) : '—'}</code> },
  ];
  return (
    <EntityPageV2 title="Запуски агентов" mode="view" breadcrumbs={[{ label: 'Запуски агентов' }]}>
      <Tab title="Список" id="list" layout="full">
        <DataTable columns={columns} data={runs} keyField="agent_execution_id" loading={isLoading}
          emptyText="Нет запусков с включённым логированием." paginated pageSize={20}
          onRowClick={(run) => navigate(`/admin/agent-runs/${run.agent_execution_id}`)} />
      </Tab>
    </EntityPageV2>
  );
}
