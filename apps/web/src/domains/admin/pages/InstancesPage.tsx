/**
 * InstancesPage v2 - Управление инстансами инструментов
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toolInstancesApi, type ToolInstance } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { AdminPage, DataTable, type DataTableColumn, Badge } from '@/shared/ui';

export function InstancesPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');

  const { data: instances, isLoading, error } = useQuery({
    queryKey: qk.toolInstances.list({}),
    queryFn: () => toolInstancesApi.list({}),
  });

  const CATEGORY_LABELS: Record<string, string> = {
    llm: 'LLM',
    rag: 'RAG',
    collection: 'Collection',
    dcbox: 'DCBox',
    jira: 'Jira',
  };

  const filteredInstances = useMemo(() => {
    if (!instances) return [];
    if (!q.trim()) return instances;
    const query = q.toLowerCase();
    return instances.filter((inst: ToolInstance) =>
      inst.name?.toLowerCase().includes(query) ||
      inst.url?.toLowerCase().includes(query) ||
      inst.category?.toLowerCase().includes(query) ||
      inst.tool_group_name?.toLowerCase().includes(query)
    );
  }, [instances, q]);

  const columns: DataTableColumn<ToolInstance>[] = [
    {
      key: 'name',
      label: 'НАЗВАНИЕ',
      sortable: true,
      render: (instance) => (
        <span style={{ fontWeight: 500 }}>{instance.name}</span>
      ),
    },
    {
      key: 'tool_group',
      label: 'ГРУППА',
      width: 150,
      sortable: true,
      render: (instance) => (
        <span style={{ color: 'var(--text-secondary)' }}>
          {instance.tool_group_name || instance.tool_group_slug || '—'}
        </span>
      ),
    },
    {
      key: 'category',
      label: 'КАТЕГОРИЯ',
      width: 110,
      sortable: true,
      render: (instance) => instance.category ? (
        <Badge tone="info" size="small">
          {CATEGORY_LABELS[instance.category] || instance.category}
        </Badge>
      ) : (
        <span style={{ color: 'var(--text-secondary)' }}>—</span>
      ),
    },
    {
      key: 'url',
      label: 'URL',
      render: (instance) => (
        <code style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
          {instance.url || '—'}
        </code>
      ),
    },
    {
      key: 'is_active',
      label: 'СТАТУС',
      width: 100,
      sortable: true,
      render: (instance) => (
        <Badge tone={instance.is_active ? 'success' : 'neutral'} size="small">
          {instance.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      ),
    },
    {
      key: 'health_status',
      label: 'HEALTH',
      width: 100,
      sortable: true,
      render: (instance) => instance.health_status ? (
        <Badge
          tone={instance.health_status === 'healthy' ? 'success' : 'warn'}
          size="small"
        >
          {instance.health_status}
        </Badge>
      ) : (
        <span style={{ color: 'var(--text-secondary)' }}>—</span>
      ),
    },
  ];

  return (
    <AdminPage
      title="Инстансы"
      subtitle="Подключения к инструментам"
      searchValue={q}
      onSearchChange={setQ}
      searchPlaceholder="Поиск инстансов..."
      actions={[
        {
          label: 'Создать',
          onClick: () => navigate('/admin/instances/new'),
          variant: 'primary',
        },
      ]}
    >
      {error && (
        <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
          Не удалось загрузить инстансы. Попробуйте снова.
        </div>
      )}

      <DataTable
        columns={columns}
        data={filteredInstances}
        keyField="id"
        loading={isLoading}
        emptyText="Инстансы не найдены. Нажмите «Создать» для добавления."
        paginated
        pageSize={20}
        onRowClick={(instance: ToolInstance) => navigate(`/admin/instances/${instance.id}`)}
      />
    </AdminPage>
  );
}

export default InstancesPage;
