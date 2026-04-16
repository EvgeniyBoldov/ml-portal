/**
 * SandboxSessionPage — fullscreen session workspace.
 * Three-column layout: sidebar | chat | config panel.
 * Read-only for non-owners.
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSandboxSession } from '../hooks/useSandboxSession';
import { useSandboxRun } from '../hooks/useSandboxRun';
import { useCatalogData } from '../hooks/useSandboxNavigation';
import { useAuth } from '@/shared/hooks/useAuth';
import { qk } from '@/shared/api/keys';
import Badge from '@/shared/ui/Badge';
import Button from '@/shared/ui/Button';
import { sandboxApi } from '../api';
import SessionSidebar from '../components/SessionSidebar';
import RunChat from '../components/RunChat';
import ConfigPanel from '../components/ConfigPanel';
import ConfirmWriteDialog from '../components/ConfirmWriteDialog';
import type { SandboxSelectedItem } from '../types';
import type { RunStep } from '../hooks/useSandboxRun';
import styles from './SandboxSessionPage.module.css';

export default function SandboxSessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { data: session, isLoading, isError } = useSandboxSession(sessionId);
  const { data: catalog } = useCatalogData(sessionId);
  const queryClient = useQueryClient();
  const [selectedItem, setSelectedItem] = useState<SandboxSelectedItem | null>(null);
  const [activeBranchId, setActiveBranchId] = useState<string>('');
  const sandboxRun = useSandboxRun(sessionId ?? '');

  // Inspector state: steps + selected step for right panel
  const [inspectorSteps, setInspectorSteps] = useState<RunStep[]>([]);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [inspectorRunId, setInspectorRunId] = useState<string | null>(null);

  const { data: branches = [] } = useQuery({
    queryKey: qk.sandbox.branches.list(sessionId ?? ''),
    queryFn: () => sandboxApi.listBranches(sessionId ?? ''),
    enabled: Boolean(sessionId),
    staleTime: 30_000,
  });

  useEffect(() => {
    if (!activeBranchId && branches.length > 0) {
      setActiveBranchId(branches[0].id);
    }
  }, [activeBranchId, branches]);

  const resetRun = sandboxRun.reset;
  useEffect(() => {
    if (!activeBranchId) {
      return;
    }
    resetRun();
  }, [activeBranchId, resetRun]);

  const { data: allRuns = [] } = useQuery({
    queryKey: qk.sandbox.runs.list(sessionId ?? ''),
    queryFn: () => sandboxApi.listRuns(sessionId ?? ''),
    enabled: Boolean(sessionId),
    staleTime: 15_000,
  });

  const forkBranchMutation = useMutation({
    mutationFn: (payload: {
      sourceBranchId: string;
      parentRunId?: string | null;
      sourceText: string;
    }) => {
      const branchName = `branch-${branches.length + 1}`;
      return sandboxApi.forkBranch(sessionId ?? '', payload.sourceBranchId, {
        name: branchName,
        parent_run_id: payload.parentRunId ?? undefined,
        copy_overrides: true,
      });
    },
    onSuccess: async (newBranch) => {
      setActiveBranchId(newBranch.id);
      await queryClient.invalidateQueries({ queryKey: qk.sandbox.branches.list(sessionId ?? '') });
      await queryClient.invalidateQueries({ queryKey: qk.sandbox.runs.list(sessionId ?? '') });
    },
  });

  if (isLoading) {
    return <div className={styles.loading}>Загрузка сессии...</div>;
  }

  if (isError || !session || !sessionId) {
    return (
      <div className={styles.error}>
        <span>Сессия не найдена</span>
        <Button onClick={() => navigate('/admin/sandbox')}>К списку</Button>
      </div>
    );
  }

  const isOwner = user?.id === session.owner_id;
  const isReadOnly = !isOwner;

  const handleRun = (text: string, parentRunId?: string | null, attachmentIds?: string[]) => {
    if (isReadOnly) return;
    sandboxRun.run(text, parentRunId, activeBranchId || undefined, attachmentIds);
  };

  const handleSelectRun = (runId?: string) => {
    setSelectedItem({ type: 'run', id: runId ?? 'active', name: 'Лог выполнения' });
  };

  const handleSelectStep = (runId: string, stepId: string, steps: RunStep[]) => {
    setInspectorSteps(steps);
    setSelectedStepId(stepId);
    setInspectorRunId(runId === 'active' ? sandboxRun.activeRun.runId : runId);
    setSelectedItem({ type: 'run', id: runId, name: 'Детали шага' });
  };

  const handleCreateBranchFromMessage = async (
    sourceText: string,
    parentRunId?: string | null,
  ): Promise<void> => {
    if (!sessionId || !activeBranchId || !sourceText.trim()) {
      return;
    }
    await forkBranchMutation.mutateAsync({
      sourceBranchId: activeBranchId,
      parentRunId,
      sourceText,
    });
  };

  return (
    <div className={styles.layout}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles['header-left']}>
          <button
            className={styles['back-btn']}
            onClick={() => navigate('/admin/sandbox')}
          >
            ← Назад
          </button>
          <span className={styles['session-name']}>{session.name}</span>
          <div className={styles['header-meta']}>
            <Badge
              tone={session.status === 'active' ? 'success' : 'neutral'}
            >
              {session.status === 'active' ? 'Активна' : 'Архив'}
            </Badge>
            {isReadOnly && (
              <span className={styles['readonly-badge']}>Только чтение</span>
            )}
          </div>
        </div>
        <div className={styles['header-right']}>
          <div className={styles['session-info']}>
            <span className={styles['session-info-item']}>TTL: {session.ttl_days} дн.</span>
            <span className={styles['session-info-item']}>
              Истекает: {new Date(session.expires_at).toLocaleDateString('ru-RU')}
            </span>
            <span className={styles['session-info-item']}>{session.owner_email}</span>
          </div>
          {isOwner && (
            <Button
              size="sm"
              variant="ghost"
              onClick={sandboxRun.stop}
              disabled={!sandboxRun.isRunning}
            >
              Стоп
            </Button>
          )}
        </div>
      </div>

      {/* Sidebar */}
      <div className={styles.sidebar}>
        <SessionSidebar
          sessionId={sessionId}
          session={session}
          branches={branches}
          activeBranchId={activeBranchId}
          runs={allRuns}
          activeRunId={sandboxRun.activeRun.runId}
          selectedItem={selectedItem}
          onSelectBranch={setActiveBranchId}
          onSelectItem={setSelectedItem}
        />
      </div>

      {/* Chat area */}
      <div className={styles['chat-area']}>
        <RunChat
          sessionId={sessionId}
          branches={branches}
          activeBranchId={activeBranchId}
          branchRuns={allRuns}
          activeRun={sandboxRun.activeRun}
          isRunning={sandboxRun.isRunning}
          isWaitingInput={sandboxRun.isWaitingInput}
          isReadOnly={isReadOnly}
          isCreatingBranch={forkBranchMutation.isPending}
          onSelectBranch={setActiveBranchId}
          onCreateBranchFromMessage={handleCreateBranchFromMessage}
          onRun={handleRun}
          onStop={sandboxRun.stop}
          onSelectRun={handleSelectRun}
          onSelectStep={handleSelectStep}
        />
      </div>

      {/* Config panel */}
      <div className={styles['config-panel']}>
        <ConfigPanel
          sessionId={sessionId}
          overrides={session.overrides}
          isReadOnly={isReadOnly}
          selectedItem={selectedItem}
          activeBranchId={activeBranchId}
          catalog={catalog}
          inspectorSteps={inspectorSteps}
          selectedStepId={selectedStepId}
          inspectorRunId={inspectorRunId}
          inspectorRunStatus={sandboxRun.activeRun.status}
        />
      </div>

      {/* Write confirmation dialog */}
      {sandboxRun.isWaitingConfirmation &&
        sandboxRun.activeRun.pendingConfirmation && (
          <ConfirmWriteDialog
            event={sandboxRun.activeRun.pendingConfirmation}
            onConfirm={() => sandboxRun.confirmAction(true)}
            onReject={() => sandboxRun.confirmAction(false)}
          />
        )}
    </div>
  );
}
