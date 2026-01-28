/**
 * RoutingLogsPage - View agent routing decisions logs
 */
import { useQuery } from '@tanstack/react-query';
import { http } from '@/shared/api/client';
import { AdminPage } from '@/shared/ui';
import Badge from '@/shared/ui/Badge';
import DataTable, { type DataTableColumn } from '@/shared/ui/DataTable/DataTable';
import styles from './RegistryPage.module.css';

interface RoutingLog {
  id: string;
  agent_id: string;
  user_id: string;
  tenant_id?: string;
  execution_mode: 'full' | 'partial' | 'unavailable';
  available_tools: string[];
  unavailable_tools: string[];
  reason?: string;
  created_at: string;
}

async function fetchRoutingLogs(params: { limit?: number; offset?: number }): Promise<RoutingLog[]> {
  const searchParams = new URLSearchParams();
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.offset) searchParams.set('offset', String(params.offset));
  const res = await http.get(`/api/v1/admin/routing-logs?${searchParams}`);
  return res.json();
}

const MODE_VARIANTS: Record<string, 'success' | 'warning' | 'error'> = {
  full: 'success',
  partial: 'warning',
  unavailable: 'error',
};

const MODE_LABELS: Record<string, string> = {
  full: 'Полный',
  partial: 'Частичный',
  unavailable: 'Недоступен',
};

export function RoutingLogsPage() {
  const { data: logs, isLoading } = useQuery({
    queryKey: ['routing-logs'],
    queryFn: () => fetchRoutingLogs({ limit: 100, offset: 0 }),
  });

  const columns: DataTableColumn<RoutingLog>[] = [
    {
      key: 'created_at',
      label: 'Время',
      width: 160,
      render: (row) => new Date(row.created_at).toLocaleString('ru-RU'),
    },
    {
      key: 'agent_id',
      label: 'Агент',
      render: (row) => <code className={styles.code}>{row.agent_id.slice(0, 8)}...</code>,
    },
    {
      key: 'user_id',
      label: 'Пользователь',
      render: (row) => <code className={styles.code}>{row.user_id.slice(0, 8)}...</code>,
    },
    {
      key: 'execution_mode',
      label: 'Режим',
      width: 120,
      render: (row) => (
        <Badge variant={MODE_VARIANTS[row.execution_mode] || 'secondary'}>
          {MODE_LABELS[row.execution_mode] || row.execution_mode}
        </Badge>
      ),
    },
    {
      key: 'available_tools',
      label: 'Доступные',
      render: (row) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {row.available_tools?.slice(0, 2).map(tool => (
            <Badge key={tool} variant="success">{tool}</Badge>
          ))}
          {(row.available_tools?.length || 0) > 2 && (
            <Badge variant="outline">+{row.available_tools.length - 2}</Badge>
          )}
          {!row.available_tools?.length && <span className={styles.muted}>—</span>}
        </div>
      ),
    },
    {
      key: 'unavailable_tools',
      label: 'Недоступные',
      render: (row) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {row.unavailable_tools?.slice(0, 2).map(tool => (
            <Badge key={tool} variant="error">{tool}</Badge>
          ))}
          {(row.unavailable_tools?.length || 0) > 2 && (
            <Badge variant="outline">+{row.unavailable_tools.length - 2}</Badge>
          )}
          {!row.unavailable_tools?.length && <span className={styles.muted}>—</span>}
        </div>
      ),
    },
  ];

  return (
    <AdminPage
      title="Routing Logs"
      subtitle="Логи решений маршрутизатора"
    >
      <div className={styles.tableWrap}>
          <DataTable
            columns={columns}
            data={logs || []}
            keyField="id"
            loading={isLoading}
            emptyText="Нет логов"
            searchable
            searchPlaceholder="Поиск..."
            paginated
            pageSize={50}
          />
      </div>
    </AdminPage>
  );
}

export default RoutingLogsPage;
