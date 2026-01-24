/**
 * RoutingLogsPage - View agent routing decisions logs
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { http } from '@/shared/api/client';
import Badge from '@/shared/ui/Badge';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import styles from './PromptRegistryPage.module.css';

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
  const [limit] = useState(50);
  const [offset, setOffset] = useState(0);

  const { data: logs, isLoading, error } = useQuery({
    queryKey: ['routing-logs', { limit, offset }],
    queryFn: () => fetchRoutingLogs({ limit, offset }),
  });

  if (isLoading) {
    return (
      <div className={styles.wrap}>
        <Skeleton variant="card" />
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.wrap}>
        <Alert variant="error" title="Ошибка загрузки" description={String(error)} />
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Routing Logs</h1>
          <p className={styles.description}>
            Логи решений маршрутизатора агентов
          </p>
        </div>
      </div>

      {!logs?.length ? (
        <Alert
          variant="info"
          title="Нет логов"
          description="Логи появятся после выполнения запросов к агентам"
        />
      ) : (
        <div className={styles.list}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Время</th>
                <th>Агент</th>
                <th>Пользователь</th>
                <th>Режим</th>
                <th>Доступные инструменты</th>
                <th>Недоступные</th>
                <th>Причина</th>
              </tr>
            </thead>
            <tbody>
              {logs.map(log => (
                <tr key={log.id}>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                  <td>
                    <code style={{ fontSize: '0.875rem' }}>
                      {log.agent_id.slice(0, 8)}...
                    </code>
                  </td>
                  <td>
                    <code style={{ fontSize: '0.875rem' }}>
                      {log.user_id.slice(0, 8)}...
                    </code>
                  </td>
                  <td>
                    <Badge variant={MODE_VARIANTS[log.execution_mode] || 'secondary'}>
                      {MODE_LABELS[log.execution_mode] || log.execution_mode}
                    </Badge>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                      {log.available_tools?.slice(0, 3).map(tool => (
                        <Badge key={tool} variant="success">{tool}</Badge>
                      ))}
                      {(log.available_tools?.length || 0) > 3 && (
                        <Badge variant="outline">+{log.available_tools.length - 3}</Badge>
                      )}
                      {!log.available_tools?.length && '—'}
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                      {log.unavailable_tools?.slice(0, 2).map(tool => (
                        <Badge key={tool} variant="error">{tool}</Badge>
                      ))}
                      {(log.unavailable_tools?.length || 0) > 2 && (
                        <Badge variant="outline">+{log.unavailable_tools.length - 2}</Badge>
                      )}
                      {!log.unavailable_tools?.length && '—'}
                    </div>
                  </td>
                  <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {log.reason || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', marginTop: '1rem' }}>
            <button
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={offset === 0}
              style={{ padding: '0.5rem 1rem', cursor: offset === 0 ? 'not-allowed' : 'pointer' }}
            >
              ← Назад
            </button>
            <span style={{ padding: '0.5rem' }}>
              {offset + 1} - {offset + (logs?.length || 0)}
            </span>
            <button
              onClick={() => setOffset(offset + limit)}
              disabled={(logs?.length || 0) < limit}
              style={{ padding: '0.5rem 1rem', cursor: (logs?.length || 0) < limit ? 'not-allowed' : 'pointer' }}
            >
              Вперёд →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default RoutingLogsPage;
