import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
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
  useEffect(() => {
    if (searchParams.get('tab') === 'memory') {
      setSearchParams((current) => {
        const next = new URLSearchParams(current);
        next.set('tab', 'agents');
        return next;
      }, { replace: true });
    }
  }, [searchParams, setSearchParams]);
  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['admin', 'agent-runs'], queryFn: agentRunsApi.list, staleTime: 15_000,
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
  return (
    <EntityPageV2 title="Запуски агентов" mode="view" defaultTab="agents" onTabChange={(tab) => {
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
    </EntityPageV2>
  );
}
