/**
 * AgentRunsPage - Список запусков агентов
 * 
 * Паттерн: PoliciesListPage (EntityPageV2 + Tab + DataTable)
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { agentRunsApi, type AgentRun, type AgentRunFilter } from '@/shared/api/agentRuns';
import { qk } from '@/shared/api/keys';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage/EntityPageV2';
import { DataTable, type DataTableColumn, Badge, Input } from '@/shared/ui';
import { RowActions } from '@/shared/ui/RowActions';
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

export function AgentRunsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState<AgentRunFilter>({
    page: 1,
    page_size: 20,
  });

  const { data: runsData, isLoading } = useQuery({
    queryKey: qk.agentRuns.list({ ...filters }),
    queryFn: () => agentRunsApi.list(filters),
  });

  const filteredRuns = useMemo(() => {
    const items = runsData?.items || [];
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter(r =>
      r.agent_slug.toLowerCase().includes(q) ||
      r.status.toLowerCase().includes(q) ||
      r.id.toLowerCase().includes(q)
    );
  }, [runsData?.items, search]);

  const columns: DataTableColumn<AgentRun>[] = [
    {
      key: 'agent_slug',
      label: 'АГЕНТ',
      render: (run) => (
        <div>
          <div style={{ fontWeight: 500 }}>{run.agent_slug}</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            {run.id.substring(0, 8)}...
          </div>
        </div>
      ),
    },
    {
      key: 'status',
      label: 'СТАТУС',
      width: 120,
      render: (run) => (
        <Badge tone={getStatusProps('run', run.status).tone as 'info' | 'success' | 'warn' | 'danger' | 'neutral'}>
          {getStatusProps('run', run.status).label}
        </Badge>
      ),
    },
    {
      key: 'total_steps',
      label: 'ШАГИ',
      width: 80,
      render: (run) => <span>{run.total_steps}</span>,
    },
    {
      key: 'total_tool_calls',
      label: 'ВЫЗОВЫ',
      width: 90,
      render: (run) => <span>{run.total_tool_calls}</span>,
    },
    {
      key: 'duration_ms',
      label: 'ВРЕМЯ',
      width: 100,
      render: (run) => (
        <span style={{ color: 'var(--text-muted)' }}>{formatDuration(run.duration_ms)}</span>
      ),
    },
    {
      key: 'started_at',
      label: 'НАЧАТ',
      width: 150,
      render: (run) => (
        <span style={{ color: 'var(--text-muted)' }}>{formatDate(run.started_at)}</span>
      ),
    },
    {
      key: 'actions',
      label: '',
      width: 60,
      align: 'right',
      render: (run) => (
        <RowActions
          actions={[
            { label: 'Открыть', onClick: () => navigate(`/admin/agent-runs/${run.id}`) },
          ]}
        />
      ),
    },
  ];

  return (
    <EntityPageV2
      title="Запуски агентов"
      mode="view"
      headerActions={
        <Input
          placeholder="Поиск по агенту..."
          value={search}
          onChange={setSearch}
        />
      }
    >
      <Tab title="Запуски" layout="full">
        <DataTable
          columns={columns}
          data={filteredRuns}
          keyField="id"
          loading={isLoading}
          emptyText="Запуски не найдены"
          onRowClick={(run) => navigate(`/admin/agent-runs/${run.id}`)}
          paginated
          pageSize={filters.page_size}
          currentPage={filters.page}
          totalItems={runsData?.total}
          onPageChange={(page) => setFilters({ ...filters, page })}
        />
      </Tab>
    </EntityPageV2>
  );
}
