/** Live sandbox run state backed by the canonical journal and named SSE frames. */
import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { consumeSse, type SseFrame } from '@/shared/api/sse';
import { sandboxApi } from '../api';
import type {
  RuntimeProgress,
  RuntimeJournalEvent,
  SandboxPause,
  SandboxRunCreate,
  SandboxStreamEvent,
  SandboxFinalAttachment,
} from '../types';
import { applyRuntimeJournalEvent, emptySandboxTrace, replayRuntimeJournal, type SandboxTraceState } from '../traceState';

type RunStatus = 'idle' | 'running' | 'completed' | 'cancelled' | 'error' | 'waiting_confirmation' | 'waiting_input';

export interface ActiveRun {
  runId: string | null;
  id?: string | null;
  requestText: string;
  startedAt: string;
  trace: SandboxTraceState;
  progress: RuntimeProgress[];
  finalContent: string;
  finalAttachments: SandboxFinalAttachment[];
  error: string | null;
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
  finalAttachments: [],
  error: null,
  status: 'idle',
  pendingConfirmation: null,
};

const MEMORY_TRACE_POLL_INTERVAL_MS = 1_000;
const MEMORY_TRACE_POLL_ATTEMPTS = 60;

const hasMemoryWriteEnded = (events: RuntimeJournalEvent[]): boolean => events.some((event) => (
  event.event_type === 'status' && event.payload.stage === 'memory_write_end'
));

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

function toFinalAttachments(value: unknown): SandboxFinalAttachment[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value.flatMap((item) => {
    const record = asRecord(item);
    const artifactId = asString(record?.artifact_id);
    const fileName = asString(record?.file_name);
    if (!artifactId || !fileName || seen.has(artifactId)) return [];
    seen.add(artifactId);
    return [{
      artifactId,
      fileName,
      downloadUrl: asString(record?.download_url) ?? undefined,
      contentType: asString(record?.content_type) ?? undefined,
      sizeBytes: asNumber(record?.size_bytes) ?? undefined,
    }];
  });
}

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
  if (frame.event === 'final' && runId) return { type: 'final', runId, content: asString(payload.content) ?? '', attachments: toFinalAttachments(payload.attachments) };
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

/**
 * Some sandbox streams contain the canonical HITL journal event but do not
 * contain the legacy `pause` SSE frame. Keep the UI responsive to both forms
 * of the protocol so clarification/confirmation controls are not lost.
 */
export function pauseFromJournalEvent(journal: RuntimeJournalEvent): SandboxPause | null {
  const reason = journal.event_type === 'waiting_input'
    ? 'waiting_input'
    : journal.event_type === 'confirmation_required'
      ? 'waiting_confirmation'
      : null;
  if (!reason) return null;

  const payload = journal.payload;
  const payloadAction = asRecord(payload.action) ?? {};
  const payloadContext = asRecord(payload.context) ?? {};
  const question = asString(payload.question) ?? asString(payloadContext.question) ?? asString(payloadAction.question);
  const message = asString(payload.message) ?? asString(payloadContext.message) ?? asString(payloadAction.message);
  const contractVersion = asNumber(payload.contract_version)
    ?? asNumber(payloadContext.contract_version)
    ?? asNumber(payloadAction.contract_version)
    ?? 1;

  return {
    run_id: journal.run_id,
    reason,
    action: {
      kind: reason === 'waiting_confirmation' ? 'confirm' : 'input',
      type: 'resume',
      reason,
      question,
      message,
      ...payloadAction,
    },
    context: {
      ...payloadContext,
      ...(question ? { question } : {}),
      ...(message ? { message } : {}),
      contract_version: contractVersion,
    },
    contract_version: contractVersion,
  };
}

export function shouldApplyJournalPause(receivedPauseFrame: boolean): boolean {
  return !receivedPauseFrame;
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
    let receivedPauseFrame = false;
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
        const journalPause = pauseFromJournalEvent(event.journal);
        if (journalPause && shouldApplyJournalPause(receivedPauseFrame)) {
          paused = true;
          setActiveRun((prev) => ({
            ...prev,
            trace: applyRuntimeJournalEvent(prev.trace, event.journal),
            status: journalPause.reason,
            pendingConfirmation: journalPause,
            finalContent: '',
            finalAttachments: [],
          }));
          finalContent = '';
        } else {
          setActiveRun((prev) => ({ ...prev, trace: applyRuntimeJournalEvent(prev.trace, event.journal) }));
        }
      } else if (event.type === 'delta') {
        streamedRunId = event.runId;
        finalContent += event.content;
        setActiveRun((prev) => ({ ...prev, finalContent }));
      } else if (event.type === 'final') {
        streamedRunId = event.runId;
        finalContent = event.content || finalContent;
        setActiveRun((prev) => ({ ...prev, finalContent, finalAttachments: event.attachments }));
      } else if (event.type === 'pause') {
        streamedRunId = event.pause.run_id;
        paused = true;
        receivedPauseFrame = true;
        setActiveRun((prev) => ({
          ...prev,
          status: event.pause.reason,
          pendingConfirmation: event.pause,
          finalContent: '',
          finalAttachments: [],
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

  const followMemoryTrace = useCallback(async (runId: string | null) => {
    if (!runId) return;
    for (let attempt = 0; attempt < MEMORY_TRACE_POLL_ATTEMPTS; attempt += 1) {
      try {
        const detail = await sandboxApi.getRunDetail(sessionId, runId);
        setActiveRun((prev) => prev.runId === runId ? {
          ...prev,
          trace: replayRuntimeJournal(detail.events),
        } : prev);
        if (hasMemoryWriteEnded(detail.events)) {
          qc.invalidateQueries({ queryKey: ['sandbox', 'branch-artifacts'] });
          return;
        }
      } catch {
        return;
      }
      await new Promise<void>((resolve) => window.setTimeout(resolve, MEMORY_TRACE_POLL_INTERVAL_MS));
    }
  }, [qc, sessionId]);

  const invalidate = useCallback((branchId?: string | null) => {
    qc.invalidateQueries({ queryKey: qk.sandbox.runs.list(sessionId) });
    if (branchId) qc.invalidateQueries({ queryKey: qk.sandbox.runs.list(sessionId, branchId) });
    qc.invalidateQueries({ queryKey: qk.sandbox.sessions.detail(sessionId) });
    qc.invalidateQueries({ queryKey: ['sandbox', 'branch-artifacts'] });
  }, [qc, sessionId]);

  const run = useCallback(async (
    requestText: string,
    parentRunId?: string | null,
    branchId?: string | null,
    artifactIds?: string[],
  ) => {
    abortRef.current?.abort();
    setActiveRun({ ...INITIAL_RUN, requestText, startedAt: new Date().toISOString(), status: 'running' });
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const { fetchStreamWithAuth } = await import('@/shared/api/streamAuth');
      const body: SandboxRunCreate = {
        request_text: requestText, branch_id: branchId ?? undefined, parent_run_id: parentRunId ?? undefined,
        artifact_ids: artifactIds?.length ? artifactIds : undefined, execution_mode: 'normal',
      };
      const response = await fetchStreamWithAuth(`/sandbox/sessions/${sessionId}/run`, { body, signal: controller.signal });
      if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
      const runId = await consumeRunStream(response);
      await reconcileTrace(runId);
      void followMemoryTrace(runId);
    } catch (error) {
      if ((error as Error).name !== 'AbortError') setActiveRun((prev) => ({ ...prev, status: 'error' }));
    } finally { invalidate(branchId); }
  }, [consumeRunStream, followMemoryTrace, invalidate, reconcileTrace, sessionId]);

  const resumePausedRun = useCallback(async (action: 'input' | 'confirm', userInput?: string) => {
    if (!activeRun.runId) return false;
    const expectedAction = activeRun.pendingConfirmation?.reason === 'waiting_input' ? 'input' : 'confirm';
    if (action !== expectedAction) {
      setActiveRun((prev) => ({ ...prev, error: 'Состояние ожидания изменилось. Повторите действие.' }));
      return false;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const request = action === 'input' ? { action, input: userInput } : { action };
      const response = await sandboxApi.resumeRun(sessionId, activeRun.runId, request, controller.signal);
      if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
      setActiveRun((prev) => ({ ...prev, status: 'running', pendingConfirmation: null, progress: [], error: null }));
      const runId = await consumeRunStream(response);
      await reconcileTrace(runId ?? activeRun.runId);
      void followMemoryTrace(runId ?? activeRun.runId);
      return true;
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        const message = error instanceof Error ? error.message : 'Ошибка возобновления';
        setActiveRun((prev) => ({ ...prev, error: message }));
        return false;
      }
      return false;
    } finally { invalidate(); }
  }, [activeRun.pendingConfirmation?.reason, activeRun.runId, consumeRunStream, followMemoryTrace, invalidate, reconcileTrace, sessionId]);

  const cancelPausedRun = useCallback(async () => {
    if (!activeRun.runId) return false;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = activeRun.status === 'waiting_input' || activeRun.status === 'waiting_confirmation'
        ? await sandboxApi.resumeRun(sessionId, activeRun.runId, { action: 'cancel' }, controller.signal)
        : await sandboxApi.cancelRun(sessionId, activeRun.runId, controller.signal);
      if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
      setActiveRun((prev) => ({ ...prev, error: null }));
      const runId = await consumeRunStream(response);
      await reconcileTrace(runId ?? activeRun.runId);
      return true;
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        const message = error instanceof Error ? error.message : 'Ошибка отмены';
        setActiveRun((prev) => ({ ...prev, error: message }));
      }
      return false;
    } finally {
      invalidate();
    }
  }, [activeRun.runId, consumeRunStream, invalidate, reconcileTrace, sessionId]);

  const stop = useCallback(() => {
    const runId = activeRun.runId;
    // Persist cancellation before closing SSE. The backend also handles a
    // transport-level CancelledError, but this makes an explicit Stop
    // distinguishable from an accidental browser disconnect.
    if (runId) {
      void sandboxApi.cancelRun(sessionId, runId).catch(() => undefined);
    }
    abortRef.current?.abort();
    setActiveRun((prev) => ({ ...prev, status: prev.status === 'running' ? 'cancelled' : prev.status }));
  }, [activeRun.runId, sessionId]);
  const reset = useCallback(() => { abortRef.current?.abort(); setActiveRun(INITIAL_RUN); }, []);

  return {
    activeRun,
    runs: activeRun.runId ? [{ id: activeRun.runId, requestText: activeRun.requestText, startedAt: activeRun.startedAt, status: activeRun.status, finalContent: activeRun.finalContent } satisfies SandboxRun] : [],
    activeRunId: activeRun.runId,
    setActiveRunId: (_id: string | null) => {},
    isRunning: activeRun.status === 'running',
    isWaitingConfirmation: activeRun.status === 'waiting_confirmation' && activeRun.pendingConfirmation !== null,
    isWaitingInput: activeRun.status === 'waiting_input',
    run, stop, reset, resumePausedRun, cancelPausedRun,
  };
}
