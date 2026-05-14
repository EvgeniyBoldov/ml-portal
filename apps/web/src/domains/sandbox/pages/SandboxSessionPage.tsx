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
import type { VirtualInspectorStep } from '../components/RunChat';
import ConfigPanel from '../components/ConfigPanel';
import ConfirmWriteDialog from '../components/ConfirmWriteDialog';
import type { SandboxSelectedItem } from '../types';
import type { RunStep } from '../hooks/useSandboxRun';
import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import styles from './SandboxSessionPage.module.css';

const SIDEBAR_WIDTH_KEY = 'sandbox.sidebar.width';
const CONFIG_WIDTH_KEY = 'sandbox.config.width';
const HANDLE_WIDTH = 8;
const SIDEBAR_MIN = 220;
const SIDEBAR_MAX = 520;
const CONFIG_MIN = 260;
const CONFIG_MAX = 680;
const CHAT_MIN = 420;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export default function SandboxSessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { data: session, isLoading, isError } = useSandboxSession(sessionId);
  const { data: catalog } = useCatalogData(sessionId);
  const queryClient = useQueryClient();
  const [selectedItem, setSelectedItem] = useState<SandboxSelectedItem | null>(null);
  const [activeBranchId, setActiveBranchId] = useState<string>('');
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const raw = window.localStorage.getItem(SIDEBAR_WIDTH_KEY);
    const parsed = raw ? Number(raw) : NaN;
    return Number.isFinite(parsed) ? parsed : 280;
  });
  const [configWidth, setConfigWidth] = useState<number>(() => {
    const raw = window.localStorage.getItem(CONFIG_WIDTH_KEY);
    const parsed = raw ? Number(raw) : NaN;
    return Number.isFinite(parsed) ? parsed : 320;
  });
  const [isCompactLayout, setIsCompactLayout] = useState<boolean>(window.innerWidth < 1200);
  
  // Inspector state: steps + selected step for right panel
  const [inspectorSteps, setInspectorSteps] = useState<RunStep[]>([]);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<TraceEntity | null>(null); // New hierarchical entity
  
  const sandboxRun = useSandboxRun(sessionId ?? '');

  const { data: branches = [] } = useQuery({
    queryKey: qk.sandbox.branches.list(sessionId ?? ''),
    queryFn: () => sandboxApi.listBranches(sessionId ?? ''),
    enabled: Boolean(sessionId),
    staleTime: 30_000,
  });

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

  const isOwner = user?.id === session?.owner_id;
  const isReadOnly = !isOwner;

  const handleRun = (text: string, parentRunId?: string | null, attachmentIds?: string[]) => {
    if (isReadOnly) return;
    sandboxRun.run(text, parentRunId, activeBranchId || undefined, attachmentIds);
  };

  const handleSelectRun = (runId?: string) => {
    setSelectedItem({ type: 'run', id: runId ?? 'active', name: 'Лог выполнения' });
  };

  const handleSelectStep = async (runId: string, stepId: string, virtualStep: VirtualInspectorStep, steps: RunStep[], entity?: TraceEntity) => {
    setInspectorSteps(steps);
    setSelectedStepId(stepId);
    setSelectedEntity(entity ?? null);
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

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth));
  }, [sidebarWidth]);

  useEffect(() => {
    window.localStorage.setItem(CONFIG_WIDTH_KEY, String(configWidth));
  }, [configWidth]);

  useEffect(() => {
    const onResize = () => setIsCompactLayout(window.innerWidth < 1200);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Early returns after all hooks are called
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

  const startSidebarResize = () => {
    const onMove = (event: PointerEvent) => {
      const viewport = window.innerWidth;
      const maxLeft = Math.min(SIDEBAR_MAX, viewport - configWidth - CHAT_MIN - HANDLE_WIDTH * 2);
      setSidebarWidth(clamp(event.clientX, SIDEBAR_MIN, Math.max(SIDEBAR_MIN, maxLeft)));
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const startConfigResize = () => {
    const onMove = (event: PointerEvent) => {
      const viewport = window.innerWidth;
      const rawRight = viewport - event.clientX;
      const maxRight = Math.min(CONFIG_MAX, viewport - sidebarWidth - CHAT_MIN - HANDLE_WIDTH * 2);
      setConfigWidth(clamp(rawRight, CONFIG_MIN, Math.max(CONFIG_MIN, maxRight)));
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const gridColumns = isCompactLayout
    ? '280px minmax(0, 1fr) 320px'
    : `${sidebarWidth}px ${HANDLE_WIDTH}px minmax(${CHAT_MIN}px, 1fr) ${HANDLE_WIDTH}px ${configWidth}px`;

  return (
    <div className={styles.layout} style={{ gridTemplateColumns: gridColumns }}>
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
      {!isCompactLayout && (
        <div
          className={styles.resizer}
          role="separator"
          aria-label="Resize sidebar"
          onPointerDown={startSidebarResize}
        />
      )}

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
          onSelectStep={(runId, stepId, virtualStep, steps, entity) => {
            void handleSelectStep(runId, stepId, virtualStep, steps, entity);
          }}
        />
      </div>
      {!isCompactLayout && (
        <div
          className={styles.resizer}
          role="separator"
          aria-label="Resize config panel"
          onPointerDown={startConfigResize}
        />
      )}

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
          selectedEntity={selectedEntity}
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
