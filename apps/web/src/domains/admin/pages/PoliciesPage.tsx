/**
 * PoliciesPage - Ограничения доступа для агентов
 */
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


export function PoliciesPage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
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

  const filteredPolicies = policies || [];

  const columns: DataTableColumn[] = [
    {
      key: 'name',
      label: 'Название',
      render: (row) => (
        <div className={styles.cellStack}>
          <span className={styles.cellPrimary}>
            {row.name || `Ограничение #${row.id.slice(0, 8)}`}
          </span>
          <code className={styles.code}>{row.id.slice(0, 8)}...</code>
        </div>
      ),
    },
    {
      key: 'allowed_tools',
      label: 'Разрешённые инструменты',
      render: (row) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {row.allowed_tools?.slice(0, 3).map((tool: string) => (
            <Badge key={tool} variant="success">{tool}</Badge>
          ))}
          {(row.allowed_tools?.length || 0) > 3 && (
            <Badge variant="outline">+{row.allowed_tools.length - 3}</Badge>
          )}
          {!row.allowed_tools?.length && <span className={styles.muted}>Все</span>}
        </div>
      ),
    },
    {
      key: 'denied_tools',
      label: 'Запрещённые',
      render: (row) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {row.denied_tools?.slice(0, 2).map((tool: string) => (
            <Badge key={tool} variant="error">{tool}</Badge>
          ))}
          {(row.denied_tools?.length || 0) > 2 && (
            <Badge variant="outline">+{row.denied_tools.length - 2}</Badge>
          )}
          {!row.denied_tools?.length && <span className={styles.muted}>—</span>}
        </div>
      ),
    },
    {
      key: 'is_active',
      label: 'Статус',
      width: 100,
      render: (row) => (
        <Badge variant={row.is_active ? 'success' : 'secondary'}>
          {row.is_active ? 'Активно' : 'Неактивно'}
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
          onDelete={() => deleteMutation.mutate(row.id)}
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
            <h1 className={styles.title}>Ограничения</h1>
            <p className={styles.subtitle}>Настройка доступа к инструментам для агентов</p>
          </div>
          <div className={styles.controls}>
            <Link to="/admin/policies/new">
              <Button>Создать</Button>
            </Link>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <DataTable
            columns={columns}
            data={filteredPolicies}
            keyField="id"
            loading={isLoading}
            emptyText="Нет ограничений"
            searchable
            searchPlaceholder="Поиск..."
          />
        </div>
      </div>
    </div>
  );
}

export default PoliciesPage;
