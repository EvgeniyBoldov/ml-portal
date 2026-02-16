/**
 * AgentListPage - Список агентов (контейнеры)
 */
import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { agentsApi, type Agent } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage/EntityPageV2';
import { DataTable, type DataTableColumn, Badge, Button, Input } from '@/shared/ui';

export function AgentListPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');

  const { data: agents, isLoading, error } = useQuery({
    queryKey: qk.agents.list({ q: q || undefined }),
    queryFn: () => agentsApi.list(),
    staleTime: 60000,
  });

  const filteredAgents = useMemo(() => {
    if (!agents) return [];
    if (!q.trim()) return agents;
    const query = q.toLowerCase();
    return agents.filter((a: Agent) =>
      a.name.toLowerCase().includes(query) ||
      a.slug.toLowerCase().includes(query)
    );
  }, [agents, q]);

  const columns: DataTableColumn<Agent>[] = [
    {
      key: 'slug',
      label: 'SLUG / ИМЯ',
      sortable: true,
      render: (agent) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{agent.slug}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{agent.name}</span>
        </div>
      ),
    },
    {
      key: 'current_version_id',
      label: 'ВЕРСИЯ',
      width: 120,
      render: (agent) => agent.current_version_id ? (
        <Badge tone="success">Активна</Badge>
      ) : (
        <Badge tone="neutral">Нет версии</Badge>
      ),
    },
    {
      key: 'description',
      label: 'ОПИСАНИЕ',
      render: (agent) => (
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
          {agent.description || '—'}
        </span>
      ),
    },
    {
      key: 'created_at',
      label: 'СОЗДАН',
      width: 120,
      sortable: true,
      render: (agent) => (
        <span style={{ color: 'var(--text-secondary)' }}>
          {new Date(agent.created_at).toLocaleDateString('ru-RU')}
        </span>
      ),
    },
  ];

  return (
    <EntityPageV2
      title="Агенты"
      mode="view"
      breadcrumbs={[
        { label: 'Агенты' },
      ]}
      headerActions={
        <Input
          placeholder="Поиск агентов..."
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />
      }
    >
      <Tab 
        title="Список" 
        layout="full"
        actions={[
          <Button key="router" variant="outline" onClick={() => navigate('/admin/agents/router')}>
            Agent Router
          </Button>,
          <Button key="create" onClick={() => navigate('/admin/agents/new')}>
            Создать агента
          </Button>,
        ]}
      >
        {error && (
          <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
            Не удалось загрузить агентов. Попробуйте снова.
          </div>
        )}

        <DataTable
          columns={columns}
          data={filteredAgents}
          keyField="id"
          loading={isLoading}
          emptyText="Агенты не найдены. Нажмите «Создать агента» для создания."
          paginated
          pageSize={20}
          onRowClick={(agent: Agent) => navigate(`/admin/agents/${agent.slug}`)}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default AgentListPage;
