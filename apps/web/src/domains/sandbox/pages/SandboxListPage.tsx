/**
 * SandboxListPage — list of sandbox sessions for admins.
 * Accessible at /admin/sandbox.
 */
import { useNavigate } from 'react-router-dom';
import { useSandboxSessions, useDeleteSession } from '../hooks/useSandboxSession';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import DataTable from '@/shared/ui/DataTable/DataTable';
import type { DataTableColumn } from '@/shared/ui/DataTable/DataTable';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
import EmptyState from '@/shared/ui/EmptyState';
import { useToast } from '@/shared/ui/Toast';
import { useState } from 'react';
import type { SandboxSessionListItem } from '../types';
import styles from './SandboxListPage.module.css';

export default function SandboxListPage() {
  const navigate = useNavigate();
  const { data: sessions = [], isLoading } = useSandboxSessions({ status: 'active' });
  const deleteSession = useDeleteSession();
  const { showToast } = useToast();
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const handleCreate = () => {
    navigate('/sandbox');
  };

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await deleteSession.mutateAsync(deleteId);
      showToast('Сессия удалена', 'success');
    } catch {
      showToast('Не удалось удалить сессию', 'error');
    } finally {
      setDeleteId(null);
    }
  };

  const columns: DataTableColumn<SandboxSessionListItem>[] = [
    {
      key: 'name',
      title: 'Название',
      render: (row) => (
        <span
          className={styles['session-name']}
          onClick={() => navigate(`/admin/sandbox/${row.id}`)}
        >
          {row.name}
        </span>
      ),
    },
    {
      key: 'owner_email',
      title: 'Владелец',
      render: (row) => (
        <div className={styles['owner-cell']}>
          <span className={styles['owner-email']}>{row.owner_email}</span>
        </div>
      ),
    },
    {
      key: 'status',
      title: 'Статус',
      render: (row) => (
        <Badge tone={row.status === 'active' ? 'success' : 'neutral'}>
          {row.status === 'active' ? 'Активна' : 'Архив'}
        </Badge>
      ),
    },
    {
      key: 'overrides_count',
      title: 'Оверрайды',
      render: (row) => <span>{row.overrides_count}</span>,
    },
    {
      key: 'runs_count',
      title: 'Запуски',
      render: (row) => <span>{row.runs_count}</span>,
    },
    {
      key: 'expires_at',
      title: 'Истекает',
      render: (row) => (
        <span className={styles['meta-label']}>
          {new Date(row.expires_at).toLocaleDateString('ru-RU')}
        </span>
      ),
    },
    {
      key: 'actions',
      title: '',
      render: (row) => (
        <div className={styles.actions}>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => navigate(`/admin/sandbox/${row.id}`)}
          >
            Открыть
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setDeleteId(row.id)}
          >
            Удалить
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Песочницы</h1>
          <p className={styles.subtitle}>
            Тестирование агентов с phantom-конфигурациями
          </p>
        </div>
        <div className={styles.actions}>
          <Button onClick={handleCreate}>
            Создать сессию
          </Button>
        </div>
      </div>

      {!isLoading && sessions.length === 0 ? (
        <div className={styles.empty}>
          <div className={styles['empty-title']}>Нет активных сессий</div>
          <div className={styles['empty-text']}>
            Создайте сессию, чтобы начать тестирование агентов с изменёнными конфигурациями
          </div>
          <Button onClick={handleCreate}>
            Создать первую сессию
          </Button>
        </div>
      ) : (
        <div className={styles['table-wrapper']}>
          <DataTable
            columns={columns}
            data={sessions}
            loading={isLoading}
            idField="id"
            onRowClick={(row) => navigate(`/sandbox/${row.id}`)}
          />
        </div>
      )}

      <ConfirmDialog
        open={!!deleteId}
        title="Удалить сессию?"
        message="Все оверрайды и запуски в этой сессии будут удалены. Это действие необратимо."
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  );
}
