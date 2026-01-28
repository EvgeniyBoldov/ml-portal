/**
 * InstancesPage - Управление инстансами инструментов
 * 
 * Единый стиль с остальными админ-реестрами.
 * Клик по строке → View страница, редактирование через кнопку на View.
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toolInstancesApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { AdminPage } from '@/shared/ui';
import Badge from '@/shared/ui/Badge';
import { AdminTable, type AdminTableColumn } from '@/shared/ui/AdminTable';

interface ToolInstance {
  id: string;
  tool_id: string;
  tool?: { name: string };
  is_active: boolean;
  health_status?: string;
  last_health_check?: string;
}

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
      inst.tool?.name?.toLowerCase().includes(query) ||
      inst.id.toLowerCase().includes(query) ||
      inst.tool_id.toLowerCase().includes(query)
    );
  }, [instances, q]);

  const handleRowClick = (instance: ToolInstance) => {
    navigate(`/admin/instances/${instance.id}`);
  };

  const columns: AdminTableColumn<ToolInstance>[] = [
    {
      key: 'tool',
      label: 'ИНСТРУМЕНТ',
      sortable: true,
      sortFn: (a, b) => (a.tool?.name || a.tool_id).localeCompare(b.tool?.name || b.tool_id),
      render: (instance) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>
            {instance.tool?.name || instance.tool_id.slice(0, 8)}
          </span>
          <code style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
            {instance.id.slice(0, 8)}...
          </code>
        </div>
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
          tone={instance.health_status === 'healthy' ? 'success' : 'danger'} 
          size="small"
        >
          {instance.health_status}
        </Badge>
      ) : (
        <span style={{ color: 'var(--muted)' }}>—</span>
      ),
    },
    {
      key: 'last_health_check',
      label: 'ПОСЛЕДНЯЯ ПРОВЕРКА',
      sortable: true,
      render: (instance) => (
        <span style={{ color: 'var(--muted)' }}>
          {instance.last_health_check 
            ? new Date(instance.last_health_check).toLocaleString('ru-RU')
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

      <AdminTable
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
