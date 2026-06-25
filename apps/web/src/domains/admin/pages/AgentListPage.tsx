/**
 * AgentListPage - Список агентов (контейнеры)
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAgentList } from '@/shared/api/hooks';
import { type Agent } from '@/shared/api/agents';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { DataTable, type DataTableColumn, Button, Input, LifecycleStatusBadge } from '@/shared/ui';

export function AgentListPage() {
  const navigate = useNavigate();
  const { filtered: filteredAgents, isLoading, search, setSearch, goToCreate, goToDetail } = useAgentList(true);

  const columns: DataTableColumn<Agent>[] = [
    {
      key: 'slug',
      label: 'SLUG / ИМЯ',
      sortable: true,
      filter: {
        kind: 'text',
        placeholder: 'Slug или имя',
        getValue: (agent) => `${agent.slug ?? ''} ${agent.name ?? ''}`,
      },
      render: (agent) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{agent.slug}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{agent.name}</span>
        </div>
      ),
    },
    {
      key: 'lifecycle_status',
      label: 'СТАТУС',
      width: 120,
      filter: {
        kind: 'select',
        placeholder: 'Все статусы',
        options: [
          { value: 'active', label: 'Active' },
          { value: 'deprecated', label: 'Deprecated' },
        ],
        getValue: (agent) => agent.lifecycle_status ?? 'active',
      },
      render: (agent) => (
        <LifecycleStatusBadge
          lifecycleStatus={agent.lifecycle_status}
          deprecatedAt={agent.deprecated_at}
          retentionDays={agent.retention_days}
        />
      ),
    },
    {
      key: 'current_version_number',
      label: 'ОСН. ВЕРСИЯ',
      width: 120,
      filter: {
        kind: 'select',
        placeholder: 'Все варианты',
        options: [
          { value: 'has_version', label: 'Есть основная версия' },
          { value: 'no_version', label: 'Нет основной версии' },
        ],
        getValue: (agent) => (agent.current_version_number != null ? 'has_version' : 'no_version'),
      },
      render: (agent) => agent.current_version_number != null ? `v${agent.current_version_number}` : '—',
    },
    {
      key: 'description',
      label: 'ОПИСАНИЕ',
      filter: {
        kind: 'text',
        placeholder: 'Описание',
        getValue: (agent) => agent.description ?? '',
      },
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
      filter: {
        kind: 'date-range',
        fromPlaceholder: 'От',
        toPlaceholder: 'До',
        getValue: (agent) => agent.created_at,
      },
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Input
            placeholder="Поиск агентов..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      }
    >
      <Tab 
        title="Список" 
        layout="full"
        actions={[
          <Button key="create" onClick={goToCreate}>
            Создать агента
          </Button>,
        ]}
      >
        <DataTable
          columns={columns}
          data={filteredAgents}
          keyField="id"
          loading={isLoading}
          emptyText="Агенты не найдены. Нажмите «Создать агента» для создания."
          paginated
          pageSize={20}
          onRowClick={goToDetail}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default AgentListPage;
