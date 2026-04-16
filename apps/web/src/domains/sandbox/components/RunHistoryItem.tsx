/**
 * RunHistoryItem — renders a single historical run with question, steps, and answer.
 * Lazy-loads run detail (steps) on expand.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { sandboxApi } from '../api';
import type { SandboxRunListItem, SandboxBranchListItem } from '../types';
import type { RunStep } from '../hooks/useSandboxRun';
import ChatQuestionCard from './ChatQuestionCard';
import ChatStepsContainer from './ChatStepsContainer';
import ChatAnswerCard from './ChatAnswerCard';
import styles from './RunHistoryItem.module.css';

interface Props {
  sessionId: string;
  run: SandboxRunListItem;
  branch?: SandboxBranchListItem;
  isCurrentBranch: boolean;
  activeBranchId: string;
}

function extractFinalContent(steps: Array<{ step_type: string; step_data: Record<string, unknown> }>): string {
  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    if (step.step_type === 'final' || step.step_type === 'final_content') {
      const content = step.step_data.content;
      if (typeof content === 'string') return content;
    }
  }
  // Fallback: concatenate deltas
  let result = '';
  for (const step of steps) {
    if (step.step_type === 'delta' && typeof step.step_data.content === 'string') {
      result += step.step_data.content;
    }
  }
  return result;
}

function apiStepsToRunSteps(steps: Array<{ id: string; step_type: string; step_data: Record<string, unknown>; order_num: number; created_at: string }>): RunStep[] {
  return steps.map((s) => ({
    id: s.id,
    type: s.step_type as RunStep['type'],
    data: s.step_data,
    timestamp: new Date(s.created_at).getTime(),
  }));
}

export default function RunHistoryItem({ sessionId, run, branch, isCurrentBranch }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);

  const { data: runDetail, isLoading } = useQuery({
    queryKey: qk.sandbox.runs.detail(sessionId, run.id),
    queryFn: () => sandboxApi.getRunDetail(sessionId, run.id),
    enabled: isExpanded && run.status !== 'running',
    staleTime: 60_000,
  });

  const steps = runDetail ? apiStepsToRunSteps(runDetail.steps) : [];
  const finalContent = runDetail ? extractFinalContent(runDetail.steps) : '';
  const isCompleted = run.status === 'completed';
  const isFailed = run.status === 'failed';

  return (
    <div className={`${styles.item} ${isExpanded ? styles['item-expanded'] : ''}`}>
      <button
        type="button"
        className={styles.header}
        onClick={() => setIsExpanded((prev) => !prev)}
        aria-expanded={isExpanded}
      >
        <div className={styles['header-top']}>
          <span className={`${styles.status} ${styles[`status-${run.status}`]}`}>
            {run.status}
          </span>
          {branch ? (
            <span
              className={`${styles.branch} ${
                isCurrentBranch ? styles['branch-current'] : styles['branch-inherited']
              }`}
            >
              {isCurrentBranch ? 'Текущая ветка' : `Унаследовано: ${branch.name}`}
            </span>
          ) : null}
          <span className={styles.time}>
            {new Date(run.started_at).toLocaleString('ru-RU')}
          </span>
          <span className={styles['run-id']}>{run.id.slice(0, 8)}</span>
          {run.steps_count > 0 ? (
            <span className={styles['steps-badge']}>{run.steps_count} шагов</span>
          ) : null}
          <span className={`${styles.chevron} ${isExpanded ? styles['chevron-open'] : ''}`}>▾</span>
        </div>
      </button>

      <ChatQuestionCard text={run.request_text} />

      {isExpanded ? (
        <div className={styles.detail}>
          {isLoading ? (
            <div className={styles.loading}>Загрузка шагов...</div>
          ) : (
            <>
              {steps.length > 0 ? (
                <ChatStepsContainer steps={steps} />
              ) : null}
              {(isCompleted || isFailed) ? (
                <ChatAnswerCard
                  text={isFailed ? (runDetail?.error ?? 'Ошибка выполнения') : finalContent}
                  isRunning={false}
                />
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
