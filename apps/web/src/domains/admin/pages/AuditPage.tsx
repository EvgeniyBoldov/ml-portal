/**
 * AuditPage - Audit logs viewer with DataTable
 */
import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminApi, type AuditLog } from '@shared/api';
import { qk } from '@shared/api/keys';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { DataTable, type DataTableColumn, Badge, Input, Button, Modal, Select } from '@/shared/ui';

const AUDIT_STATUS_OPTIONS = [
  { value: '', label: 'Все статусы' },
  { value: 'success', label: 'Success' },
  { value: 'error', label: 'Error' },
];

export function AuditPage() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [action, setAction] = useState('');
  const [userId, setUserId] = useState('');
  const [status, setStatus] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  const filters = useMemo(() => ({
    page,
    page_size: pageSize,
    action: action || undefined,
    user_id: userId || undefined,
    status: status || undefined,
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
  }), [page, pageSize, action, userId, status, fromDate, toDate]);

  const { data, isLoading, error } = useQuery({
    queryKey: qk.admin.audit(filters),
    queryFn: () => adminApi.getAuditLogs(filters),
    staleTime: 30000,
  });

  const logs = data?.items || [];
  const total = data?.total || logs.length;

  const resetFilters = () => {
    setPage(1);
    setAction('');
    setUserId('');
    setStatus('');
    setFromDate('');
    setToDate('');
  };

  const columns: DataTableColumn<AuditLog>[] = [
    {
      key: 'ts',
      label: 'Время',
      width: 180,
      render: (log) => (
        <span style={{ color: 'var(--muted)' }}>
          {new Date(log.created_at || log.ts || '').toLocaleString('ru-RU', {
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
        return <Badge tone={tone}>{log.action}</Badge>;
      },
    },
    {
      key: 'actor_user_id',
      label: 'Пользователь',
      width: 120,
      render: (log) => (
        <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', background: 'var(--bg-subtle)', padding: '2px 6px', borderRadius: '4px' }}>
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
        <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', background: 'var(--bg-subtle)', padding: '2px 6px', borderRadius: '4px' }}>{log.ip || '—'}</code>
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
    <EntityPageV2
      title="Аудит"
      mode="view"
      headerActions={
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          <Input
            placeholder="Действие..."
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setPage(1);
            }}
          />
          <Input
            placeholder="User..."
            value={userId}
            onChange={(e) => {
              setUserId(e.target.value);
              setPage(1);
            }}
          />
          <Select
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={AUDIT_STATUS_OPTIONS}
            placeholder="Статус"
            style={{ minWidth: 160 }}
          />
          <Input
            type="date"
            value={fromDate}
            onChange={(e) => {
              setFromDate(e.target.value);
              setPage(1);
            }}
            placeholder="От"
          />
          <Input
            type="date"
            value={toDate}
            onChange={(e) => {
              setToDate(e.target.value);
              setPage(1);
            }}
            placeholder="До"
          />
          <Button variant="outline" onClick={resetFilters}>
            Сбросить
          </Button>
        </div>
      }
    >
      <Tab title="Журнал" layout="full">
        {error && (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--danger)' }}>
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
      </Tab>

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
              <strong>Время:</strong> {new Date(selectedLog.created_at || selectedLog.ts || '').toLocaleString('ru-RU')}
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
    </EntityPageV2>
  );
}

export default AuditPage;
