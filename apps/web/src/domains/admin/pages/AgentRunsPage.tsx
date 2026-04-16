/**
 * AgentRunsPage - Список запусков агентов
 * 
 * Паттерн: PoliciesListPage (EntityPageV2 + Tab + DataTable)
 */
import { useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { agentRunsApi, type AgentRun, type AgentRunFilter } from '@/shared/api/agentRuns';
import { qk } from '@/shared/api/keys';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { DataTable, type DataTableColumn, Badge, Input } from '@/shared/ui';
import { RowActions } from '@/shared/ui/RowActions';
import { getStatusProps } from '@/shared/lib/statusConfig';
import styles from './AgentRunsPage.module.css';

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
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [chatId, setChatId] = useState(() => searchParams.get('chat_id') ?? '');
  const [filters, setFilters] = useState<AgentRunFilter>({
    page: 1,
    page_size: 20,
  });

  const effectiveFilters = useMemo<AgentRunFilter>(() => {
    const next: AgentRunFilter = { ...filters };
    if (chatId.trim()) {
      next.chat_id = chatId.trim();
    } else {
      delete next.chat_id;
    }
    return next;
  }, [filters, chatId]);

  const { data: runsData, isLoading } = useQuery({
    queryKey: qk.agentRuns.list({ ...effectiveFilters }),
    queryFn: () => agentRunsApi.list(effectiveFilters),
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
        <div className={styles['agent-cell']}>
          <div className={styles['agent-slug']}>{run.agent_slug}</div>
          <div className={styles['agent-id']}>{run.id.substring(0, 8)}...</div>
        </div>
      ),
    },
    {
      key: 'chat_id',
      label: 'ЧАТ',
      width: 140,
      render: (run) => (
        <span className={styles.muted}>
          {run.chat_id ? `${run.chat_id.substring(0, 8)}...` : '—'}
        </span>
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
        <span className={styles.muted}>{formatDuration(run.duration_ms)}</span>
      ),
    },
    {
      key: 'started_at',
      label: 'НАЧАТ',
      width: 150,
      render: (run) => (
        <span className={styles.muted}>{formatDate(run.started_at)}</span>
      ),
    },
    {
      key: 'actions',
      label: '',
      width: 60,
      align: 'right',
      render: (run) => (
        <RowActions
          basePath="/admin/agent-runs"
          id={run.id}
          editable={false}
          deletable={false}
          customActions={run.chat_id ? [{
            label: 'Все рансы чата',
            onClick: () => {
              setChatId(run.chat_id!);
              setFilters(prev => ({ ...prev, page: 1 }));
              setSearchParams({ chat_id: run.chat_id! });
            },
          }] : []}
        />
      ),
    },
  ];

  return (
    <EntityPageV2
      title="Запуски агентов"
      mode="view"
      headerActions={
        <div className={styles.filters}>
          <div className={styles['filter-item']}>
            <Input
              placeholder="Поиск по агенту/статусу/ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className={styles['filter-item']}>
            <Input
              placeholder="Фильтр: chat_id (UUID)"
              value={chatId}
              onChange={(e) => {
                const next = e.target.value;
                setChatId(next);
                setFilters(prev => ({ ...prev, page: 1 }));
                if (next.trim()) {
                  setSearchParams({ chat_id: next.trim() });
                } else {
                  setSearchParams({});
                }
              }}
            />
          </div>
        </div>
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
          pageSize={effectiveFilters.page_size}
          currentPage={effectiveFilters.page}
          totalItems={runsData?.total}
          onPageChange={(page) => setFilters({ ...filters, page })}
        />
      </Tab>
    </EntityPageV2>
  );
}
