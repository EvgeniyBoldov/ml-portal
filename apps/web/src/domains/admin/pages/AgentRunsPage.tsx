import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentRunsApi, AgentRun, AgentRunDetail, AgentRunFilter } from '@/shared/api';
import Button from '@/shared/ui/Button';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './AgentRunsPage.module.css';

function formatDuration(ms?: number): string {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function StatusBadge({ status }: { status: string }) {
  const className = {
    running: styles.statusRunning,
    completed: styles.statusCompleted,
    failed: styles.statusFailed,
  }[status] || styles.statusRunning;

  return <span className={`${styles.statusBadge} ${className}`}>{status}</span>;
}

function StepItem({ step }: { step: AgentRunDetail['steps'][0] }) {
  const [expanded, setExpanded] = useState(false);
  
  const stepClass = {
    llm_request: styles.stepLlm,
    tool_call: styles.stepToolCall,
    tool_result: styles.stepToolResult,
    final_response: styles.stepFinal,
  }[step.step_type] || '';

  const stepIcon = {
    llm_request: '🤖',
    tool_call: '🔧',
    tool_result: '📤',
    final_response: '✅',
  }[step.step_type] || '📝';

  const dataPreview = JSON.stringify(step.data).slice(0, 100);

  return (
    <div className={`${styles.step} ${stepClass} ${expanded ? styles.stepExpanded : ''}`}>
      <div 
        className={styles.stepHeader} 
        onClick={() => setExpanded(!expanded)}
        style={{ cursor: 'pointer' }}
      >
        <span className={styles.stepIcon}>{stepIcon}</span>
        <span className={styles.stepType}>
          #{step.step_number + 1} {step.step_type.replace(/_/g, ' ')}
        </span>
        <span className={styles.stepTime}>
          {step.duration_ms ? `${step.duration_ms}ms` : ''}
        </span>
        <span className={styles.stepToggle}>{expanded ? '▼' : '▶'}</span>
      </div>
      {!expanded && (
        <div className={styles.stepPreview}>
          {dataPreview}{dataPreview.length >= 100 ? '...' : ''}
        </div>
      )}
      {expanded && (
        <pre className={styles.stepData}>
          {JSON.stringify(step.data, null, 2)}
        </pre>
      )}
    </div>
  );
}

function RunDetailModal({ 
  run, 
  onClose 
}: { 
  run: AgentRunDetail; 
  onClose: () => void;
}) {
  return (
    <div className={styles.modal} onClick={onClose}>
      <div className={styles.modalContent} onClick={e => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>Run Details</h2>
          <button className={styles.modalClose} onClick={onClose}>&times;</button>
        </div>
        <div className={styles.modalBody}>
          <div className={styles.runMeta}>
            <div className={styles.metaItem}>
              <span className={styles.metaLabel}>Agent</span>
              <span className={styles.metaValue}>{run.agent_slug}</span>
            </div>
            <div className={styles.metaItem}>
              <span className={styles.metaLabel}>Status</span>
              <StatusBadge status={run.status} />
            </div>
            <div className={styles.metaItem}>
              <span className={styles.metaLabel}>Duration</span>
              <span className={styles.metaValue}>{formatDuration(run.duration_ms)}</span>
            </div>
            <div className={styles.metaItem}>
              <span className={styles.metaLabel}>Steps</span>
              <span className={styles.metaValue}>{run.total_steps}</span>
            </div>
            <div className={styles.metaItem}>
              <span className={styles.metaLabel}>Tool Calls</span>
              <span className={styles.metaValue}>{run.total_tool_calls}</span>
            </div>
            <div className={styles.metaItem}>
              <span className={styles.metaLabel}>Started</span>
              <span className={styles.metaValue}>{formatDate(run.started_at)}</span>
            </div>
            {run.error && (
              <div className={styles.metaItem} style={{ gridColumn: '1 / -1' }}>
                <span className={styles.metaLabel}>Error</span>
                <span className={styles.metaValue} style={{ color: 'var(--danger)' }}>
                  {run.error}
                </span>
              </div>
            )}
          </div>

          <h3 className={styles.stepsTitle}>Steps ({run.steps?.length || 0})</h3>
          <div className={styles.stepsList}>
            {run.steps?.length ? (
              run.steps.map((step) => (
                <StepItem key={step.id} step={step} />
              ))
            ) : (
              <div className={styles.noSteps}>No steps recorded for this run</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function AgentRunsPage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [filters, setFilters] = useState<AgentRunFilter>({
    page: 1,
    page_size: 20,
  });
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const { data: runsData, isLoading } = useQuery({
    queryKey: ['agent-runs', filters],
    queryFn: () => agentRunsApi.list(filters),
  });

  const { data: selectedRun, isLoading: isLoadingDetail } = useQuery({
    queryKey: ['agent-runs', selectedRunId],
    queryFn: () => agentRunsApi.get(selectedRunId!),
    enabled: !!selectedRunId,
  });

  const { data: stats } = useQuery({
    queryKey: ['agent-runs', 'stats'],
    queryFn: () => agentRunsApi.getStats(),
  });

  const deleteMutation = useMutation({
    mutationFn: (runId: string) => agentRunsApi.delete(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent-runs'] });
      showSuccess('Run deleted');
    },
    onError: () => showError('Failed to delete run'),
  });

  const deleteOldMutation = useMutation({
    mutationFn: (beforeDate: string) => agentRunsApi.deleteOld(beforeDate),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['agent-runs'] });
      showSuccess(`Deleted ${data.deleted_count} runs`);
    },
    onError: () => showError('Failed to delete old runs'),
  });

  const handleDeleteOld = () => {
    const days = prompt('Delete runs older than N days:', '30');
    if (!days) return;
    
    const daysNum = parseInt(days, 10);
    if (isNaN(daysNum) || daysNum < 1) {
      showError('Invalid number of days');
      return;
    }

    const beforeDate = new Date();
    beforeDate.setDate(beforeDate.getDate() - daysNum);
    
    if (confirm(`Delete all runs before ${beforeDate.toLocaleDateString()}?`)) {
      deleteOldMutation.mutate(beforeDate.toISOString());
    }
  };

  const handleDelete = (e: React.MouseEvent, runId: string) => {
    e.stopPropagation();
    if (confirm('Delete this run?')) {
      deleteMutation.mutate(runId);
    }
  };

  const totalPages = runsData ? Math.ceil(runsData.total / runsData.page_size) : 0;

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <h1 className={styles.title}>Agent Runs</h1>
        <div className={styles.headerActions}>
          <Button 
            variant="outline" 
            onClick={handleDeleteOld}
            disabled={deleteOldMutation.isPending}
          >
            Cleanup Old Runs
          </Button>
        </div>
      </div>

      {stats && (
        <div className={styles.stats}>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>Total Runs</div>
            <div className={styles.statValue}>{stats.total_runs}</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>Completed</div>
            <div className={styles.statValue}>{stats.by_status.completed || 0}</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>Failed</div>
            <div className={styles.statValue}>{stats.by_status.failed || 0}</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>Avg Duration</div>
            <div className={styles.statValue}>{formatDuration(stats.avg_duration_ms)}</div>
          </div>
        </div>
      )}

      <div className={styles.filters}>
        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Status</label>
          <select
            className={styles.filterSelect}
            value={filters.status || ''}
            onChange={e => setFilters({ ...filters, status: e.target.value || undefined, page: 1 })}
          >
            <option value="">All</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Agent</label>
          <input
            type="text"
            className={styles.filterInput}
            placeholder="e.g. chat-rag"
            value={filters.agent_slug || ''}
            onChange={e => setFilters({ ...filters, agent_slug: e.target.value || undefined, page: 1 })}
          />
        </div>
      </div>

      {isLoading ? (
        <div className={styles.emptyState}>Loading...</div>
      ) : !runsData?.items.length ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>📊</div>
          <div className={styles.emptyTitle}>No runs found</div>
          <div className={styles.emptyDescription}>
            Agent runs will appear here when agents with logging enabled are executed.
          </div>
        </div>
      ) : (
        <>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Status</th>
                <th>Steps</th>
                <th>Tool Calls</th>
                <th>Duration</th>
                <th>Started</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runsData.items.map((run) => (
                <tr 
                  key={run.id} 
                  className={styles.clickableRow}
                  onClick={() => setSelectedRunId(run.id)}
                >
                  <td>
                    <span className={styles.agentSlug}>{run.agent_slug}</span>
                  </td>
                  <td><StatusBadge status={run.status} /></td>
                  <td>{run.total_steps}</td>
                  <td>{run.total_tool_calls}</td>
                  <td className={styles.duration}>{formatDuration(run.duration_ms)}</td>
                  <td>{formatDate(run.started_at)}</td>
                  <td>
                    <button
                      className={styles.deleteBtn}
                      onClick={(e) => handleDelete(e, run.id)}
                      disabled={deleteMutation.isPending}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {totalPages > 1 && (
            <div className={styles.pagination}>
              <Button
                variant="outline"
                disabled={filters.page === 1}
                onClick={() => setFilters({ ...filters, page: (filters.page || 1) - 1 })}
              >
                Previous
              </Button>
              <span className={styles.pageInfo}>
                Page {filters.page} of {totalPages}
              </span>
              <Button
                variant="outline"
                disabled={filters.page === totalPages}
                onClick={() => setFilters({ ...filters, page: (filters.page || 1) + 1 })}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}

      {selectedRunId && selectedRun && !isLoadingDetail && (
        <RunDetailModal
          run={selectedRun}
          onClose={() => setSelectedRunId(null)}
        />
      )}
    </div>
  );
}
