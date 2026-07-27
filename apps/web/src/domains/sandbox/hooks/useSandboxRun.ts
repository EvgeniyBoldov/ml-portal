/** Live sandbox run state backed by the canonical journal and named SSE frames. */
import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { consumeSse, type SseFrame } from '@/shared/api/sse';
import { sandboxApi } from '../api';
import type {
  RuntimeProgress,
  SandboxPause,
  SandboxRunCreate,
  SandboxStreamEvent,
} from '../types';
import { applyRuntimeJournalEvent, emptySandboxTrace, replayRuntimeJournal, type SandboxTraceState } from '../traceState';

type RunStatus = 'idle' | 'running' | 'completed' | 'error' | 'waiting_confirmation' | 'waiting_input';

export interface ActiveRun {
  runId: string | null;
  id?: string | null;
  requestText: string;
  startedAt: string;
  trace: SandboxTraceState;
  progress: RuntimeProgress[];
  finalContent: string;
  status: RunStatus;
  pendingConfirmation: SandboxPause | null;
}

const INITIAL_RUN: ActiveRun = {
  runId: null,
  id: null,
  requestText: '',
  startedAt: '',
  trace: emptySandboxTrace(),
  progress: [],
  finalContent: '',
  status: 'idle',
  pendingConfirmation: null,
};

export interface SandboxRun {
  id: string;
  requestText: string;
  startedAt: string;
  status: RunStatus;
  finalContent: string;
}

const asRecord = (value: unknown): Record<string, unknown> | null => (
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
);
const asString = (value: unknown): string | null => typeof value === 'string' ? value : null;
const asNumber = (value: unknown): number | null => typeof value === 'number' ? value : null;

function decodeSandboxFrame(frame: SseFrame): SandboxStreamEvent | null {
  if (frame.data === '[DONE]') return null;
  let payload: Record<string, unknown> | null = null;
  try { payload = asRecord(JSON.parse(frame.data)); } catch { return null; }
  if (!payload) return null;
  const runId = asString(payload.run_id) ?? '';

  if (frame.event === 'run_started' && runId) return { type: 'run_started', runId };
  if (frame.event === 'progress' && runId) {
    const phase = asString(payload.phase);
    const kind = asString(payload.kind);
    const description = asString(payload.description);
    if (phase && kind && description) return { type: 'progress', progress: { run_id: runId, phase, kind, description, status: asString(payload.status) } };
  }
  if (frame.event === 'journal') {
    const id = asString(payload.id);
    const sequence = asNumber(payload.sequence);
    const eventType = asString(payload.event_type);
    const occurredAt = asString(payload.occurred_at);
    const eventPayload = asRecord(payload.payload);
    if (id && runId && sequence !== null && eventType && occurredAt && eventPayload) {
      return { type: 'journal', journal: {
        id, run_id: runId, sequence, event_type: eventType, occurred_at: occurredAt,
        entity_type: asString(payload.entity_type), entity_id: asString(payload.entity_id),
        parent_entity_type: asString(payload.parent_entity_type), parent_entity_id: asString(payload.parent_entity_id),
        caused_by_event_id: asString(payload.caused_by_event_id), duration_ms: asNumber(payload.duration_ms), payload: eventPayload,
      } };
    }
  }
  if (frame.event === 'delta' && runId) return { type: 'delta', runId, content: asString(payload.content) ?? '' };
  if (frame.event === 'final' && runId) return { type: 'final', runId, content: asString(payload.content) ?? '' };
  if (frame.event === 'pause' && runId) {
    const reason = asString(payload.reason);
    const action = asRecord(payload.action);
    const context = asRecord(payload.context);
    const contractVersion = asNumber(payload.contract_version);
    if ((reason === 'waiting_confirmation' || reason === 'waiting_input') && action && context && contractVersion !== null) {
      return { type: 'pause', pause: { run_id: runId, reason, action, context, contract_version: contractVersion } };
    }
  }
  if (frame.event === 'error' && runId) return { type: 'error', runId, error: asString(payload.error) ?? 'Sandbox execution failed' };
  if (frame.event === 'done' && runId) return { type: 'done', runId };
  return null;
}

function appendProgress(items: RuntimeProgress[], progress: RuntimeProgress): RuntimeProgress[] {
  const last = items[items.length - 1];
  if (last?.description === progress.description && last.phase === progress.phase && last.kind === progress.kind) return items;
  return [...items, progress].slice(-10);
}

export function useSandboxRun(sessionId: string) {
  const [activeRun, setActiveRun] = useState<ActiveRun>(INITIAL_RUN);
  const abortRef = useRef<AbortController | null>(null);
  const qc = useQueryClient();

  const consumeRunStream = useCallback(async (response: Response): Promise<string | null> => {
    let finalContent = '';
    let paused = false;
    let streamedRunId: string | null = null;
    await consumeSse(response, (frame) => {
      const event = decodeSandboxFrame(frame);
      if (!event) return;
      if (event.type === 'error') throw new Error(event.error);
      if (event.type === 'run_started') {
        streamedRunId = event.runId;
        setActiveRun((prev) => ({ ...prev, runId: event.runId, id: event.runId }));
      } else if (event.type === 'progress') {
        setActiveRun((prev) => ({ ...prev, progress: appendProgress(prev.progress, event.progress) }));
      } else if (event.type === 'journal') {
        streamedRunId = event.journal.run_id;
        setActiveRun((prev) => ({ ...prev, trace: applyRuntimeJournalEvent(prev.trace, event.journal) }));
      } else if (event.type === 'delta') {
        streamedRunId = event.runId;
        finalContent += event.content;
        setActiveRun((prev) => ({ ...prev, finalContent }));
      } else if (event.type === 'final') {
        streamedRunId = event.runId;
        finalContent = event.content || finalContent;
        setActiveRun((prev) => ({ ...prev, finalContent }));
      } else if (event.type === 'pause') {
        streamedRunId = event.pause.run_id;
        paused = true;
        setActiveRun((prev) => ({
          ...prev,
          status: event.pause.reason,
          pendingConfirmation: event.pause,
          finalContent: '',
        }));
        finalContent = '';
      }
    });
    setActiveRun((prev) => ({ ...prev, status: paused ? prev.status : 'completed', finalContent }));
    return streamedRunId;
  }, []);

  const reconcileTrace = useCallback(async (runId: string | null) => {
    if (!runId) return;
    try {
      const detail = await sandboxApi.getRunDetail(sessionId, runId);
      setActiveRun((prev) => prev.runId === runId ? {
        ...prev,
        trace: replayRuntimeJournal(detail.events),
        finalContent: prev.finalContent,
      } : prev);
    } catch {
      // Live SSE remains usable when the terminal detail refresh is unavailable.
    }
  }, [sessionId]);

  const invalidate = useCallback((branchId?: string | null) => {
    qc.invalidateQueries({ queryKey: qk.sandbox.runs.list(sessionId) });
    if (branchId) qc.invalidateQueries({ queryKey: qk.sandbox.runs.list(sessionId, branchId) });
    qc.invalidateQueries({ queryKey: qk.sandbox.sessions.detail(sessionId) });
  }, [qc, sessionId]);

  const run = useCallback(async (
    requestText: string,
    parentRunId?: string | null,
    branchId?: string | null,
    attachmentIds?: string[],
  ) => {
    abortRef.current?.abort();
    setActiveRun({ ...INITIAL_RUN, requestText, startedAt: new Date().toISOString(), status: 'running' });
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const { fetchStreamWithAuth } = await import('@/shared/api/streamAuth');
      const body: SandboxRunCreate = {
        request_text: requestText, branch_id: branchId ?? undefined, parent_run_id: parentRunId ?? undefined,
        attachment_ids: attachmentIds?.length ? attachmentIds : undefined, execution_mode: 'normal',
      };
      const response = await fetchStreamWithAuth(`/sandbox/sessions/${sessionId}/run`, { body, signal: controller.signal });
      if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
      const runId = await consumeRunStream(response);
      await reconcileTrace(runId);
    } catch (error) {
      if ((error as Error).name !== 'AbortError') setActiveRun((prev) => ({ ...prev, status: 'error' }));
    } finally { invalidate(branchId); }
  }, [consumeRunStream, invalidate, reconcileTrace, sessionId]);

  const confirmAction = useCallback(async (confirmed: boolean, userInput?: string) => {
    if (!activeRun.runId) return;
    if (!confirmed) {
      await sandboxApi.confirmRunAction(sessionId, activeRun.runId, { confirmed: false });
      setActiveRun((prev) => ({ ...prev, status: 'completed', pendingConfirmation: null }));
      invalidate();
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setActiveRun((prev) => ({ ...prev, status: 'running', pendingConfirmation: null, progress: [] }));
    try {
      const response = await sandboxApi.resumeRun(sessionId, activeRun.runId, { confirmed: true, user_input: userInput }, controller.signal);
      if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
      const runId = await consumeRunStream(response);
      await reconcileTrace(runId ?? activeRun.runId);
    } catch (error) {
      if ((error as Error).name !== 'AbortError') setActiveRun((prev) => ({ ...prev, status: 'error', pendingConfirmation: null }));
    } finally { invalidate(); }
  }, [activeRun.runId, consumeRunStream, invalidate, reconcileTrace, sessionId]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setActiveRun((prev) => ({ ...prev, status: prev.status === 'running' ? 'completed' : prev.status }));
  }, []);
  const reset = useCallback(() => { abortRef.current?.abort(); setActiveRun(INITIAL_RUN); }, []);

  return {
    activeRun,
    runs: activeRun.runId ? [{ id: activeRun.runId, requestText: activeRun.requestText, startedAt: activeRun.startedAt, status: activeRun.status, finalContent: activeRun.finalContent } satisfies SandboxRun] : [],
    activeRunId: activeRun.runId,
    setActiveRunId: (_id: string | null) => {},
    isRunning: activeRun.status === 'running',
    isWaitingConfirmation: activeRun.status === 'waiting_confirmation' && activeRun.pendingConfirmation !== null,
    isWaitingInput: activeRun.status === 'waiting_input',
    run, stop, reset, confirmAction,
  };
}
