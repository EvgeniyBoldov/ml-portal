/**
 * AuditPage - Audit logs viewer
 */
import React, { useState } from 'react';
import { useAuditLog } from '@shared/api/hooks/useAdmin';
import Input from '@shared/ui/Input';
import { Skeleton } from '@shared/ui/Skeleton';
import Button from '@shared/ui/Button';
import styles from './AuditPage.module.css';

interface AuditFilters {
  actor_user_id: string;
  action: string;
  object_type: string;
  start_date: string;
  end_date: string;
}

export function AuditPage() {
  const [filters, setFilters] = useState<AuditFilters>({
    actor_user_id: '',
    action: '',
    object_type: '',
    start_date: '',
    end_date: '',
  });

  const queryParams = React.useMemo(
    () => ({
      actor_user_id: filters.actor_user_id || undefined,
      action: filters.action || undefined,
      object_type: filters.object_type || undefined,
      start_date: filters.start_date || undefined,
      end_date: filters.end_date || undefined,
      limit: 50,
    }),
    [filters]
  );

  const { data, isLoading, error } = useAuditLog(queryParams);
  const logs = data?.logs || [];

  if (error) {
    return (
      <div className={styles.wrap}>
        <div className={styles.errorState}>Failed to load audit logs.</div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <h1 className={styles.title}>Audit Log</h1>
        </div>

        <div className={styles.filters}>
          <Input
            placeholder="Actor ID"
            value={filters.actor_user_id}
            onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
              setFilters(prev => ({
                ...prev,
                actor_user_id: event.target.value,
              }))
            }
          />
          <Input
            placeholder="Action"
            value={filters.action}
            onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
              setFilters(prev => ({ ...prev, action: event.target.value }))
            }
          />
          <Input
            placeholder="Object Type"
            value={filters.object_type}
            onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
              setFilters(prev => ({
                ...prev,
                object_type: event.target.value,
              }))
            }
          />
          <Input
            type="date"
            placeholder="Start Date"
            value={filters.start_date}
            onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
              setFilters(prev => ({ ...prev, start_date: event.target.value }))
            }
          />
          <Input
            type="date"
            placeholder="End Date"
            value={filters.end_date}
            onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
              setFilters(prev => ({ ...prev, end_date: event.target.value }))
            }
          />
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>TIMESTAMP</th>
                <th>ACTOR</th>
                <th>ACTION</th>
                <th>OBJECT</th>
                <th>DETAILS</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    <td>
                      <Skeleton width={140} />
                    </td>
                    <td>
                      <Skeleton width={100} />
                    </td>
                    <td>
                      <Skeleton width={80} />
                    </td>
                    <td>
                      <Skeleton width={120} />
                    </td>
                    <td>
                      <Skeleton width={200} />
                    </td>
                  </tr>
                ))
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={5} className={styles.emptyState}>
                    No audit logs found
                  </td>
                </tr>
              ) : (
                logs.map((log, i) => (
                  <tr key={i}>
                    <td>{new Date(log.timestamp).toLocaleString()}</td>
                    <td>{log.actor_user_id?.substring(0, 8)}</td>
                    <td>{log.action}</td>
                    <td>{log.object_type}</td>
                    <td>{JSON.stringify(log.changes).substring(0, 50)}...</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {data?.has_more && (
          <div className={styles.loadMore}>
            <Button onClick={() => {}}>Load More</Button>
          </div>
        )}
      </div>
    </div>
  );
}

export default AuditPage;
