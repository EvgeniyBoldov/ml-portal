import React, { useState, useEffect, useCallback } from 'react';
import { adminApi, type AuditLog, type AuditLogListResponse } from '../../../shared/api/admin';
import Button from '../../../shared/ui/Button';
import Input from '../../../shared/ui/Input';
import Select from '../../../shared/ui/Select';
import { Skeleton } from '../../../shared/ui/Skeleton';
import { useErrorToast } from '../../../shared/ui/Toast';
import styles from './AuditPage.module.css';

export function AuditPage() {
  const showError = useErrorToast();

  // State
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | undefined>();
  const [currentCursor, setCurrentCursor] = useState<string | undefined>();

  // Filters
  const [filters, setFilters] = useState({
    actor_user_id: '',
    action: '',
    object_type: '',
    start_date: '',
    end_date: '',
  });

  // Load audit logs
  const loadLogs = useCallback(async (cursor?: string, reset = false) => {
    try {
      setLoading(true);
      
      const params = {
        actor_user_id: filters.actor_user_id || undefined,
        action: filters.action || undefined,
        object_type: filters.object_type || undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        limit: 50,
        cursor,
      };

      const response: AuditLogListResponse = await adminApi.getAuditLogs(params);
      
      if (reset) {
        setLogs(response.logs);
        setCurrentCursor(undefined);
      } else {
        setLogs(prev => [...prev, ...response.logs]);
      }
      
      setTotal(response.total);
      setHasMore(response.has_more);
      setNextCursor(response.next_cursor);
    } catch (error) {
      console.error('Failed to load audit logs:', error);
      showError('Failed to load audit logs. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [filters, showError]);

  // Load more logs
  const loadMore = useCallback(() => {
    if (hasMore && nextCursor && !loading) {
      setCurrentCursor(nextCursor);
      loadLogs(nextCursor, false);
    }
  }, [hasMore, nextCursor, loading, loadLogs]);

  // Refresh logs
  const refreshLogs = useCallback(() => {
    loadLogs(undefined, true);
  }, [loadLogs]);

  // Handle search
  const handleSearch = useCallback(() => {
    loadLogs(undefined, true);
  }, [loadLogs]);

  // Handle filter changes
  const handleFilterChange = (field: string) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    setFilters(prev => ({ ...prev, [field]: e.target.value }));
  };

  // Load logs on mount and when filters change
  useEffect(() => {
    loadLogs(undefined, true);
  }, [loadLogs]);

  // Get action badge style
  const getActionBadgeStyle = (action: string) => {
    if (action.includes('create') || action.includes('created')) return 'create';
    if (action.includes('update') || action.includes('updated')) return 'update';
    if (action.includes('delete') || action.includes('deleted')) return 'delete';
    if (action.includes('login') || action.includes('auth')) return 'login';
    return 'default';
  };

  // Get actor initials
  const getActorInitials = (actorUserId: string | undefined) => {
    if (!actorUserId) return 'S';
    return actorUserId.slice(0, 2).toUpperCase();
  };

  // Format action name
  const formatAction = (action: string) => {
    return action
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Audit Log</h1>
        <div className={styles.pageActions}>
          <Button onClick={refreshLogs} variant="outline">
            Refresh
          </Button>
        </div>
      </div>

      <div className={styles.filters}>
        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Actor</label>
          <Input
            placeholder="User ID or login..."
            value={filters.actor_user_id}
            onChange={handleFilterChange('actor_user_id')}
            className={styles.filterInput}
          />
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Action</label>
          <Input
            placeholder="Action name..."
            value={filters.action}
            onChange={handleFilterChange('action')}
            className={styles.filterInput}
          />
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Object Type</label>
          <Select
            value={filters.object_type}
            onChange={handleFilterChange('object_type')}
            className={styles.filterSelect}
          >
            <option value="">All Types</option>
            <option value="user">User</option>
            <option value="token">Token</option>
            <option value="password">Password</option>
            <option value="auth">Authentication</option>
          </Select>
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Start Date</label>
          <Input
            type="datetime-local"
            value={filters.start_date}
            onChange={handleFilterChange('start_date')}
            className={styles.filterInput}
          />
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>End Date</label>
          <Input
            type="datetime-local"
            value={filters.end_date}
            onChange={handleFilterChange('end_date')}
            className={styles.filterInput}
          />
        </div>

        <div className={styles.filterActions}>
          <Button onClick={handleSearch} variant="outline">
            Search
          </Button>
          <Button 
            onClick={() => {
              setFilters({
                actor_user_id: '',
                action: '',
                object_type: '',
                start_date: '',
                end_date: '',
              });
              loadLogs(undefined, true);
            }}
            variant="outline"
          >
            Clear
          </Button>
        </div>
      </div>

      <div className={styles.tableContainer}>
        <div className={styles.tableHeader}>
          <h2 className={styles.tableTitle}>Audit Logs</h2>
          <div className={styles.tableStats}>
            {loading ? (
              <Skeleton width={100} />
            ) : (
              `Showing ${logs.length} of ${total} logs`
            )}
          </div>
        </div>

        <div className={styles.tableContent}>
          {loading && logs.length === 0 ? (
            <div className={styles.loadingState}>
              <div className={styles.loadingSpinner} />
              <p>Loading audit logs...</p>
            </div>
          ) : logs.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyStateIcon}>📋</div>
              <div className={styles.emptyStateTitle}>No audit logs</div>
              <div className={styles.emptyStateDescription}>
                No audit logs found matching your criteria.
              </div>
            </div>
          ) : (
            <div>
              {logs.map((log) => (
                <div key={log.id} className={styles.auditItem}>
                  <div className={styles.auditInfo}>
                    <div className={styles.auditAction}>
                      <span className={`${styles.actionBadge} ${styles[getActionBadgeStyle(log.action)]}`}>
                        {formatAction(log.action)}
                      </span>
                    </div>
                    
                    <div className={styles.auditDetails}>
                      {log.object_type && log.object_id && (
                        <>
                          <span className={styles.objectType}>{log.object_type}</span>
                          <span className={styles.objectId}> ({log.object_id})</span>
                        </>
                      )}
                    </div>
                    
                    <div className={styles.auditMeta}>
                      <div className={styles.actorInfo}>
                        <div className={styles.actorAvatar}>
                          {getActorInitials(log.actor_user_id)}
                        </div>
                        <span className={log.actor_user_id ? styles.actorName : styles.systemActor}>
                          {log.actor_user_id ? `User ${log.actor_user_id.slice(0, 8)}` : 'System'}
                        </span>
                      </div>
                      
                      {log.ip && (
                        <>
                          <span>•</span>
                          <span>IP: {log.ip}</span>
                        </>
                      )}
                      
                      {log.user_agent && (
                        <>
                          <span>•</span>
                          <span title={log.user_agent}>
                            {log.user_agent.length > 50 
                              ? `${log.user_agent.slice(0, 50)}...` 
                              : log.user_agent
                            }
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  
                  <div className={styles.auditTime}>
                    {new Date(log.ts).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {hasMore && (
          <div className={styles.pagination}>
            <div className={styles.paginationInfo}>
              Showing {logs.length} of {total} logs
            </div>
            <div className={styles.paginationControls}>
              <Button
                onClick={loadMore}
                disabled={loading}
                variant="outline"
              >
                {loading ? 'Loading...' : 'Load More'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AuditPage;
