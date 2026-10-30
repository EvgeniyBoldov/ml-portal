/**
 * SandboxListPage — list of sandbox sessions for admins.
 * Accessible at /admin/sandbox.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSandboxSessions, useDeleteSession } from '../hooks/useSandboxSession';
import type { SandboxSessionListItem } from '../types';
import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  type DataTableColumn,
} from '@/shared/ui';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { useToast } from '@/shared/ui/Toast';
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
      label: 'НАЗВАНИЕ',
      sortable: true,
      render: (row) => <span className={styles['session-name']}>{row.name}</span>,
    },
    {
      key: 'owner_name',
      label: 'ВЛАДЕЛЕЦ',
      render: (row) => {
        const ownerName = row.owner_name?.trim();
        const ownerEmail = row.owner_email !== 'unknown' ? row.owner_email : null;
        const ownerLabel = ownerName || ownerEmail || 'Неизвестный пользователь';
        const fallbackId = !ownerName && !ownerEmail ? row.owner_id.slice(0, 8) : null;

        return (
          <div className={styles['owner-cell']} title={row.owner_id}>
            <span className={styles['owner-name']}>{ownerLabel}</span>
            {ownerName && ownerEmail && ownerEmail !== ownerName && (
              <span className={styles['owner-email']}>{ownerEmail}</span>
            )}
            {fallbackId && <span className={styles['owner-email']}>ID {fallbackId}</span>}
          </div>
        );
      },
    },
    {
      key: 'status',
      label: 'СТАТУС',
      render: (row) => (
        <Badge tone={row.status === 'active' ? 'success' : 'neutral'}>
          {row.status === 'active' ? 'Активна' : 'Архив'}
        </Badge>
      ),
    },
    {
      key: 'overrides_count',
      label: 'ОВЕРРАЙДЫ',
      render: (row) => row.overrides_count,
    },
    {
      key: 'runs_count',
      label: 'ЗАПУСКИ',
      render: (row) => row.runs_count,
    },
    {
      key: 'expires_at',
      label: 'ИСТЕКАЕТ',
      render: (row) => (
        <span className={styles['meta-label']}>
          {new Date(row.expires_at).toLocaleDateString('ru-RU')}
        </span>
      ),
    },
    {
      key: 'actions',
      label: 'ДЕЙСТВИЯ',
      render: (row) => (
        <div className={styles.actions}>
          <Button
            size="sm"
            variant="ghost"
            onClick={(event) => {
              event.stopPropagation();
              navigate(`/sandbox/${row.id}`);
            }}
          >
            Открыть
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(event) => {
              event.stopPropagation();
              setDeleteId(row.id);
            }}
          >
            Удалить
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <EntityPageV2
        title="Песочницы"
        subtitle="Тестирование агентов с phantom-конфигурациями"
        mode="view"
        breadcrumbs={[{ label: 'Песочницы' }]}
      >
        <Tab
          title="Список"
          layout="full"
          actions={[
            <Button key="create" onClick={handleCreate}>
              Создать сессию
            </Button>,
          ]}
        >
          <DataTable
            columns={columns}
            data={sessions}
            loading={isLoading}
            keyField="id"
            paginated
            pageSize={20}
            onRowClick={(row) => navigate(`/sandbox/${row.id}`)}
            emptyText="Активных сессий нет. Создайте сессию, чтобы начать тестирование агентов."
          />
        </Tab>
      </EntityPageV2>

      <ConfirmDialog
        open={!!deleteId}
        title="Удалить сессию?"
        message="Все оверрайды и запуски будут удалены. Это действие необратимо."
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
      />
    </>
  );
}
