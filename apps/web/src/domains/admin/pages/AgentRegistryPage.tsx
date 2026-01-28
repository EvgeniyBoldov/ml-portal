/**
 * AgentRegistryPage - Реестр агентов
 * 
 * Управление профилями агентов: системный промпт + инструменты.
 * Клик по строке → View страница, редактирование через кнопку на View.
 */
import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { agentsApi, type Agent } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { AdminPage } from '@/shared/ui';
import Badge from '@/shared/ui/Badge';
import { AdminTable, type AdminTableColumn } from '@/shared/ui/AdminTable';

export function AgentRegistryPage() {
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

  const handleRowClick = (agent: Agent) => {
    navigate(`/admin/agents/${agent.slug}`);
  };

  const columns: AdminTableColumn<Agent>[] = [
    {
      key: 'slug',
      label: 'SLUG / ИМЯ',
      sortable: true,
      render: (agent) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{agent.slug}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{agent.name}</span>
        </div>
      ),
    },
    {
      key: 'is_active',
      label: 'СТАТУС',
      width: 100,
      sortable: true,
      render: (agent) => (
        <Badge tone={agent.is_active ? 'success' : 'neutral'} size="small">
          {agent.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      ),
    },
    {
      key: 'system_prompt_slug',
      label: 'ПРОМПТ',
      sortable: true,
      render: (agent) => (
        <code style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
          {agent.system_prompt_slug || '—'}
        </code>
      ),
    },
    {
      key: 'tools',
      label: 'ИНСТРУМЕНТЫ',
      width: 120,
      render: (agent) => {
        const toolsCount = agent.tools?.length || 0;
        return toolsCount > 0 ? (
          <Badge tone="info" size="small">{toolsCount} инстр.</Badge>
        ) : (
          <span style={{ color: 'var(--muted)' }}>—</span>
        );
      },
    },
    {
      key: 'updated_at',
      label: 'ОБНОВЛЁН',
      width: 120,
      sortable: true,
      render: (agent) => (
        <span style={{ color: 'var(--muted)' }}>
          {new Date(agent.updated_at).toLocaleDateString('ru-RU')}
        </span>
      ),
    },
  ];

  return (
    <AdminPage
      title="Агенты"
      subtitle="Профили агентов: системный промпт + инструменты"
      searchValue={q}
      onSearchChange={setQ}
      searchPlaceholder="Поиск агентов..."
      actions={[
        {
          label: 'Создать агента',
          onClick: () => navigate('/admin/agents/new'),
          variant: 'primary',
        },
      ]}
    >
      {error && (
        <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
          Не удалось загрузить агентов. Попробуйте снова.
        </div>
      )}

      <AdminTable
        columns={columns}
        data={filteredAgents}
        keyField="id"
        loading={isLoading}
        emptyText="Агенты не найдены. Нажмите «Создать агента» для создания."
        paginated
        pageSize={20}
        defaultSortKey="slug"
        defaultSortDirection="asc"
        onRowClick={handleRowClick}
      />
    </AdminPage>
  );
}

export default AgentRegistryPage;
