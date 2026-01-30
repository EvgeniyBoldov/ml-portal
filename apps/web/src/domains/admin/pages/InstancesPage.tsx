/**
 * InstancesPage - Управление инстансами инструментов
 * 
 * Единый стиль с остальными админ-реестрами.
 * Клик по строке → View страница, редактирование через кнопку на View.
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

  const filteredInstances = useMemo(() => {
    if (!instances) return [];
    if (!q.trim()) return instances;
    const query = q.toLowerCase();
    return instances.filter((inst: ToolInstance) => 
      inst.name?.toLowerCase().includes(query) ||
      inst.slug?.toLowerCase().includes(query) ||
      inst.tool_group_name?.toLowerCase().includes(query)
    );
  }, [instances, q]);

  const handleRowClick = (instance: ToolInstance) => {
    navigate(`/admin/instances/${instance.id}`);
  };

  const columns: DataTableColumn<ToolInstance>[] = [
    {
      key: 'name',
      label: 'SLUG / ИМЯ',
      sortable: true,
      render: (instance) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{instance.slug}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
            {instance.name}
          </span>
        </div>
      ),
    },
    {
      key: 'tool_group',
      label: 'ГРУППА',
      width: 150,
      sortable: true,
      render: (instance) => (
        <span>{instance.tool_group_name || instance.tool_group_slug || '—'}</span>
      ),
    },
    {
      key: 'is_active',
      label: 'СТАТУС',
      width: 100,
      sortable: true,
      render: (instance) => (
        <Badge variant={instance.is_active ? 'success' : 'default'} size="small">
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
          variant={instance.health_status === 'healthy' ? 'success' : 'warning'} 
          size="small"
        >
          {instance.health_status}
        </Badge>
      ) : (
        <span style={{ color: 'var(--color-text-muted)' }}>—</span>
      ),
    },
    {
      key: 'last_health_check_at',
      label: 'ПРОВЕРКА',
      width: 150,
      sortable: true,
      render: (instance) => (
        <span style={{ color: 'var(--color-text-muted)' }}>
          {instance.last_health_check_at 
            ? new Date(instance.last_health_check_at).toLocaleString('ru-RU')
            : '—'}
        </span>
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
        onRowClick={handleRowClick}
      />
    </AdminPage>
  );
}

export default InstancesPage;
