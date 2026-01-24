/**
 * InstancesPage - Tool instances management
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toolInstancesApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import DataTable, { type DataTableColumn } from '@/shared/ui/DataTable/DataTable';
import { RowActions } from '@/shared/ui/RowActions';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './RegistryPage.module.css';

const ServerIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
    <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
    <line x1="6" y1="6" x2="6.01" y2="6"/>
    <line x1="6" y1="18" x2="6.01" y2="18"/>
  </svg>
);

export function InstancesPage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const [filter, setFilter] = useState<'all' | 'active' | 'inactive'>('all');

  const { data: instances, isLoading } = useQuery({
    queryKey: qk.toolInstances.list({}),
    queryFn: () => toolInstancesApi.list({}),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => toolInstancesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
      showSuccess('Инстанс удалён');
    },
    onError: () => showError('Ошибка удаления'),
  });

  const healthCheckMutation = useMutation({
    mutationFn: (id: string) => toolInstancesApi.healthCheck(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
      showSuccess(`Health: ${data.status}`);
    },
    onError: () => showError('Health check failed'),
  });

  const filteredInstances = instances?.filter(inst => {
    if (filter === 'active') return inst.is_active;
    if (filter === 'inactive') return !inst.is_active;
    return true;
  }) || [];

  const columns: DataTableColumn[] = [
    {
      key: 'tool',
      label: 'Инструмент',
      render: (row) => (
        <div className={styles.cellStack}>
          <span className={styles.cellPrimary} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ServerIcon />
            {row.tool?.name || row.tool_id.slice(0, 8)}
          </span>
          <code className={styles.code}>{row.id.slice(0, 8)}...</code>
        </div>
      ),
    },
    {
      key: 'is_active',
      label: 'Статус',
      width: 100,
      render: (row) => (
        <Badge variant={row.is_active ? 'success' : 'secondary'}>
          {row.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      ),
    },
    {
      key: 'health_status',
      label: 'Health',
      width: 100,
      render: (row) => (
        row.health_status ? (
          <Badge variant={row.health_status === 'healthy' ? 'success' : 'error'}>
            {row.health_status}
          </Badge>
        ) : <span className={styles.muted}>—</span>
      ),
    },
    {
      key: 'last_health_check',
      label: 'Последняя проверка',
      render: (row) => (
        row.last_health_check 
          ? new Date(row.last_health_check).toLocaleString('ru-RU')
          : <span className={styles.muted}>—</span>
      ),
    },
    {
      key: 'actions',
      label: '',
      width: 50,
      align: 'right',
      render: (row) => (
        <RowActions
          basePath="/admin/instances"
          id={row.id}
          onDelete={() => deleteMutation.mutate(row.id)}
          deleteLoading={deleteMutation.isPending}
          customActions={[
            { label: 'Health Check', onClick: () => healthCheckMutation.mutate(row.id) },
          ]}
        />
      ),
    },
  ];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Инстансы</h1>
            <p className={styles.subtitle}>Подключения к инструментам</p>
          </div>
          <div className={styles.controls}>
            <select
              value={filter}
              onChange={e => setFilter(e.target.value as typeof filter)}
              style={{ padding: '8px 12px', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)' }}
            >
              <option value="all">Все</option>
              <option value="active">Активные</option>
              <option value="inactive">Неактивные</option>
            </select>
            <Link to="/admin/instances/new">
              <Button variant="primary">Создать</Button>
            </Link>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <DataTable
            columns={columns}
            data={filteredInstances}
            keyField="id"
            loading={isLoading}
            emptyText="Нет инстансов"
            searchable
            searchPlaceholder="Поиск..."
          />
        </div>
      </div>
    </div>
  );
}

export default InstancesPage;
