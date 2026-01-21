/**
 * AuditPage - Audit logs viewer with DataTable
 */
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminApi, type AuditLog } from '@shared/api';
import { qk } from '@shared/api/keys';
import DataTable, { type DataTableColumn } from '@shared/ui/DataTable';
import Badge from '@shared/ui/Badge';
import Input from '@shared/ui/Input';
import Button from '@shared/ui/Button';
import Modal from '@shared/ui/Modal';
import styles from './RegistryPage.module.css';

export function AuditPage() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [action, setAction] = useState('');
  const [userId, setUserId] = useState('');
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: qk.admin.audit({ page, action: action || undefined, user_id: userId || undefined }),
    queryFn: () => adminApi.getAuditLogs({
      action: action || undefined,
      actor_user_id: userId || undefined,
      limit: pageSize,
    }),
    staleTime: 30000,
  });

  const logs = data?.logs || [];
  const total = data?.total || logs.length;

  const columns: DataTableColumn<AuditLog>[] = [
    {
      key: 'ts',
      label: 'Время',
      width: 180,
      render: (log) => (
        <span className={styles.muted}>
          {new Date(log.ts).toLocaleString('ru-RU', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          })}
        </span>
      ),
    },
    {
      key: 'action',
      label: 'Действие',
      width: 200,
      render: (log) => {
        const actionType = log.action.split('.')[0];
        const tone = actionType === 'mcp' ? 'info' : 
                     log.action.includes('delete') ? 'danger' :
                     log.action.includes('create') ? 'success' : 'neutral';
        return <Badge tone={tone} size="small">{log.action}</Badge>;
      },
    },
    {
      key: 'actor_user_id',
      label: 'Пользователь',
      width: 120,
      render: (log) => (
        <code className={styles.code}>
          {log.actor_user_id ? log.actor_user_id.substring(0, 8) : '—'}
        </code>
      ),
    },
    {
      key: 'object_type',
      label: 'Объект',
      width: 150,
      render: (log) => log.object_type || '—',
    },
    {
      key: 'ip',
      label: 'IP',
      width: 120,
      render: (log) => (
        <code className={styles.code}>{log.ip || '—'}</code>
      ),
    },
    {
      key: 'meta',
      label: 'Детали',
      render: (log) => (
        <Button
          variant="outline"
          size="small"
          onClick={() => setSelectedLog(log)}
        >
          Подробнее
        </Button>
      ),
    },
  ];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Аудит</h1>
            <p className={styles.subtitle}>
              Журнал действий пользователей и MCP запросов
            </p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Фильтр по действию..."
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className={styles.search}
            />
            <Input
              placeholder="User ID..."
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              className={styles.search}
            />
          </div>
        </div>

        {error && (
          <div className={styles.errorState}>
            Не удалось загрузить логи аудита
          </div>
        )}

        <DataTable
          columns={columns}
          data={logs}
          keyField="id"
          loading={isLoading}
          paginated
          pageSize={pageSize}
          currentPage={page}
          totalItems={total}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          emptyText="Логи аудита не найдены"
        />
      </div>

      {/* Details Modal */}
      {selectedLog && (
        <Modal
          open={!!selectedLog}
          onClose={() => setSelectedLog(null)}
          title="Детали лога аудита"
        >
          <div style={{ padding: '24px', maxWidth: '600px' }}>
            <div style={{ marginBottom: '16px' }}>
              <strong>ID:</strong> <code>{selectedLog.id}</code>
            </div>
            <div style={{ marginBottom: '16px' }}>
              <strong>Время:</strong> {new Date(selectedLog.ts).toLocaleString('ru-RU')}
            </div>
            <div style={{ marginBottom: '16px' }}>
              <strong>Действие:</strong> <Badge>{selectedLog.action}</Badge>
            </div>
            <div style={{ marginBottom: '16px' }}>
              <strong>Пользователь:</strong> {selectedLog.actor_user_id || '—'}
            </div>
            <div style={{ marginBottom: '16px' }}>
              <strong>Объект:</strong> {selectedLog.object_type || '—'}
            </div>
            {selectedLog.object_id && (
              <div style={{ marginBottom: '16px' }}>
                <strong>Object ID:</strong> <code>{selectedLog.object_id}</code>
              </div>
            )}
            <div style={{ marginBottom: '16px' }}>
              <strong>IP:</strong> {selectedLog.ip || '—'}
            </div>
            {selectedLog.user_agent && (
              <div style={{ marginBottom: '16px' }}>
                <strong>User Agent:</strong>
                <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '4px' }}>
                  {selectedLog.user_agent}
                </div>
              </div>
            )}
            {selectedLog.request_id && (
              <div style={{ marginBottom: '16px' }}>
                <strong>Request ID:</strong> <code>{selectedLog.request_id}</code>
              </div>
            )}
            {selectedLog.meta && Object.keys(selectedLog.meta).length > 0 && (
              <div>
                <strong>Метаданные:</strong>
                <pre style={{
                  marginTop: '8px',
                  padding: '12px',
                  background: 'var(--bg-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12px',
                  overflow: 'auto',
                  maxHeight: '300px',
                }}>
                  {JSON.stringify(selectedLog.meta, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

export default AuditPage;
