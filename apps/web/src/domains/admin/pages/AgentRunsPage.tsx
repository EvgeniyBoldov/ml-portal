import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { agentRunsApi, type AgentRunListItem } from '@/shared/api/admin';
import { listExternalRequests, type ExternalRequestListItem } from '@/shared/api/externalRequests';
import { qk } from '@/shared/api/keys';
import { DataTable, type DataTableColumn, Badge } from '@/shared/ui';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { runStatusLabel, runStatusTone } from './agentRunStatus';
import styles from './AgentRunsPage.module.css';

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
    <EntityPageV2 title="Запуски агентов" mode="view" defaultTab={searchParams.get('tab') === 'external-requests' ? 'external-requests' : 'agents'} onTabChange={(tab) => {
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
      <Tab title="Внешние запросы" id="external-requests" layout="full">
        <ExternalRequestsTable />
      </Tab>
    </EntityPageV2>
  );
}

const externalRequestPath = (id: string) => `/admin/agent-runs/external-requests/${encodeURIComponent(id)}`;

const externalRequestColumns: DataTableColumn<ExternalRequestListItem>[] = [
  { key: 'source', label: 'Источник', width: 160 },
  {
    key: 'text_preview',
    label: 'Поручение',
    render: (row) => row.text_preview.length > 180
      ? `${row.text_preview.slice(0, 180)}…`
      : row.text_preview || '—',
  },
  { key: 'user_name', label: 'Пользователь', width: 180 },
  {
    key: 'status', label: 'Статус', width: 190,
    render: (row) => <Badge tone={runStatusTone(row.status)}>{runStatusLabel[row.status] || row.status}</Badge>,
  },
  { key: 'created_at', label: 'Принято', width: 180, render: (row) => formatDate(row.created_at) },
  { key: 'updated_at', label: 'Обновлено', width: 180, render: (row) => formatDate(row.updated_at) },
  {
    key: 'run_id',
    label: 'ID запуска',
    render: (row) => (
      <Link to={externalRequestPath(row.run_id)} onClick={(event) => event.stopPropagation()}>
        <code>{row.run_id}</code>
      </Link>
    ),
  },
];

function ExternalRequestsTable() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const offset = (page - 1) * pageSize;
  const { data, isPending, isError } = useQuery({
    queryKey: qk.admin.externalRequests(pageSize, offset),
    queryFn: () => listExternalRequests(pageSize, offset),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  });

  if (isError && !data) return <p role="alert">Не удалось загрузить внешние запросы.</p>;

  return (
    <DataTable
      columns={externalRequestColumns}
      data={data?.items ?? []}
      keyField="run_id"
      rowClassName={() => styles['external-request-row']}
      onRowClick={(row) => navigate(externalRequestPath(row.run_id))}
      loading={isPending}
      emptyText="Внешних поручений пока нет."
      paginated
      serverPaginated
      currentPage={page}
      pageSize={pageSize}
      totalItems={data?.total ?? 0}
      onPageChange={setPage}
      onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
    />
  );
}
