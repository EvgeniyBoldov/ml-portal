/**
 * PoliciesPage - Permission policies management
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { permissionsApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import DataTable, { type DataTableColumn } from '@/shared/ui/DataTable/DataTable';
import { RowActions } from '@/shared/ui/RowActions';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './RegistryPage.module.css';

const SCOPE_LABELS: Record<string, string> = {
  default: 'По умолчанию',
  tenant: 'Тенант',
  user: 'Пользователь',
};

export function PoliciesPage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const [scopeFilter, setScopeFilter] = useState<string>('all');

  const { data: policies, isLoading } = useQuery({
    queryKey: qk.permissions.list({}),
    queryFn: () => permissionsApi.list({}),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => permissionsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.permissions.all() });
      showSuccess('Политика удалена');
    },
    onError: () => showError('Ошибка удаления'),
  });

  const filteredPolicies = policies?.filter(p => {
    if (scopeFilter === 'all') return true;
    return p.scope === scopeFilter;
  }) || [];

  const columns: DataTableColumn[] = [
    {
      key: 'scope',
      label: 'Уровень',
      width: 140,
      render: (row) => (
        <Badge variant={row.scope === 'default' ? 'primary' : 'secondary'}>
          {SCOPE_LABELS[row.scope] || row.scope}
        </Badge>
      ),
    },
    {
      key: 'target',
      label: 'Тенант / Пользователь',
      render: (row) => (
        row.scope === 'default' ? (
          <span className={styles.muted}>—</span>
        ) : row.scope === 'tenant' ? (
          <code className={styles.code}>{row.tenant_id?.slice(0, 8)}...</code>
        ) : (
          <code className={styles.code}>{row.user_id?.slice(0, 8)}...</code>
        )
      ),
    },
    {
      key: 'allowed_tools',
      label: 'Инструменты',
      render: (row) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {row.allowed_tools?.slice(0, 3).map((tool: string) => (
            <Badge key={tool} variant="outline">{tool}</Badge>
          ))}
          {(row.allowed_tools?.length || 0) > 3 && (
            <Badge variant="outline">+{row.allowed_tools.length - 3}</Badge>
          )}
          {!row.allowed_tools?.length && <span className={styles.muted}>—</span>}
        </div>
      ),
    },
    {
      key: 'is_active',
      label: 'Статус',
      width: 100,
      render: (row) => (
        <Badge variant={row.is_active ? 'success' : 'secondary'}>
          {row.is_active ? 'Активна' : 'Неактивна'}
        </Badge>
      ),
    },
    {
      key: 'actions',
      label: '',
      width: 50,
      align: 'right',
      render: (row) => (
        <RowActions
          basePath="/admin/policies"
          id={row.id}
          onDelete={row.scope !== 'default' ? () => deleteMutation.mutate(row.id) : undefined}
          deletable={row.scope !== 'default'}
          deleteLoading={deleteMutation.isPending}
        />
      ),
    },
  ];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Политики</h1>
            <p className={styles.subtitle}>Управление доступом к инструментам и коллекциям</p>
          </div>
          <div className={styles.controls}>
            <select
              value={scopeFilter}
              onChange={e => setScopeFilter(e.target.value)}
              style={{ padding: '8px 12px', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)' }}
            >
              <option value="all">Все уровни</option>
              <option value="default">По умолчанию</option>
              <option value="tenant">Тенант</option>
              <option value="user">Пользователь</option>
            </select>
            <Link to="/admin/policies/new">
              <Button variant="primary">Создать</Button>
            </Link>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <DataTable
            columns={columns}
            data={filteredPolicies}
            keyField="id"
            loading={isLoading}
            emptyText="Нет политик"
            searchable
            searchPlaceholder="Поиск..."
          />
        </div>
      </div>
    </div>
  );
}

export default PoliciesPage;
