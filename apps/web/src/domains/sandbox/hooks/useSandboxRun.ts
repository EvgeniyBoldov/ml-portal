/**
 * Hook for sandbox run execution via SSE streaming.
 * Session-first: runs are scoped to a sandbox session.
 */
import { useState, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { sandboxApi } from '../api';
import type { SandboxSSEEvent, SandboxRunCreate } from '../types';
import type { ExecutionMode } from '@/shared/api/types';

export type RunStepType =
  | 'user_request'
  | 'status'
  | 'llm_call'
  | 'llm_request'
  | 'llm_response'
  | 'llm_turn'
  | 'tool_call'
  | 'tool_result'
  | 'operation_call'
  | 'operation_result'
  | 'budget'
  | 'budget_snapshot'
  | 'delta'
  | 'final'
  | 'final_response'
  | 'final_content'
  | 'error'
  | 'routing'
  | 'planner_step'
  | 'planner_action'
  | 'planner_decision'
  | 'agent_result'
  | 'policy_decision'
  | 'confirmation_required'
  | 'question_answer'
  | 'answer'
  | 'waiting_input'
  | 'run_paused'
  | 'stop'
  | 'done'
  | 'intent'; // High-level intent descriptions

export interface RunStep {
  id: string;
  type: RunStepType;
  data: Record<string, unknown>;
  timestamp: number;
  orderNumber?: number;
}

export interface ActiveRun {
  runId: string | null;
  id?: string | null;
  requestText: string;
  startedAt: string;
  steps: RunStep[];
  finalContent: string;
  status: 'idle' | 'running' | 'completed' | 'error' | 'waiting_confirmation' | 'waiting_input';
  pendingConfirmation: SandboxSSEEvent | null;
}

const INITIAL_RUN: ActiveRun = {
  runId: null,
  id: null,
  requestText: '',
  startedAt: '',
  steps: [],
  finalContent: '',
  status: 'idle',
  pendingConfirmation: null,
};

export interface SandboxRun {
  id: string;
  requestText: string;
  startedAt: string;
  status: ActiveRun['status'];
  steps: RunStep[];
  finalContent: string;
}

export function useSandboxRun(sessionId: string) {
  const [activeRun, setActiveRun] = useState<ActiveRun>(INITIAL_RUN);
  const abortRef = useRef<AbortController | null>(null);
  const stepCounterRef = useRef(0);
  const qc = useQueryClient();

  const addStep = useCallback(
    (type: RunStepType, data: Record<string, unknown>) => {
      stepCounterRef.current += 1;
      const step: RunStep = {
        id: crypto.randomUUID(),
        type,
        data,
        timestamp: Date.now(),
        orderNumber: stepCounterRef.current,
      };
      setActiveRun((prev) => ({
        ...prev,
        steps: [...prev.steps, step],
      }));
    },
    [],
  );

  const run = useCallback(
    async (
      requestText: string,
      parentRunIdOrLegacy?: string | null | unknown,
      branchId?: string | null,
      attachmentIds?: string[],
      executionMode: ExecutionMode = 'normal',
    ) => {
      // Abort previous run if any
      abortRef.current?.abort();

      const parentRunId =
        typeof parentRunIdOrLegacy === 'string' || parentRunIdOrLegacy == null
          ? parentRunIdOrLegacy
          : null;

      setActiveRun({
        runId: null,
        id: null,
        requestText,
        startedAt: new Date().toISOString(),
        steps: [],
        finalContent: '',
        status: 'running',
        pendingConfirmation: null,
      });
      stepCounterRef.current = 0;

      const controller = new AbortController();
      abortRef.current = controller;

      const body: SandboxRunCreate = {
        request_text: requestText,
        branch_id: branchId ?? undefined,
        parent_run_id: parentRunId ?? undefined,
        attachment_ids: attachmentIds?.length ? attachmentIds : undefined,
        execution_mode: executionMode,
      };

      try {
        const { fetchStreamWithAuth } = await import('@/shared/api/streamAuth');
        const response = await fetchStreamWithAuth(
          `/sandbox/sessions/${sessionId}/run`,
          {
            body,
            signal: controller.signal,
          }
        );

        if (!response.ok) {
          const err = await response.text();
          throw new Error(err || `HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalContent = '';
        let runId: string | null = null;
        let isDone = false;

        while (reader && !isDone) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;
            try {
              const event = JSON.parse(raw) as SandboxSSEEvent;
              const { type, run_id, ...data } = event;

              if (run_id && !runId) {
                runId = run_id;
                setActiveRun((prev) => ({ ...prev, runId, id: runId }));
              }

              if (type === 'done') {
                isDone = true;
                addStep('done', data);
                break;
              }

              if (type === 'delta') {
                finalContent += (data.content as string) ?? '';
                setActiveRun((prev) => ({ ...prev, finalContent }));
              }
              if (type === 'final' || type === 'final_content') {
                finalContent = (data.content as string) ?? finalContent;
                setActiveRun((prev) => ({ ...prev, finalContent }));
              }

              if (type === 'confirmation_required') {
                setActiveRun((prev) => ({
                  ...prev,
                  status: 'waiting_confirmation',
                  pendingConfirmation: event,
                  finalContent: '',
                }));
                finalContent = '';
                addStep(type as RunStepType, data);
                continue;
              }

              if (type === 'waiting_input') {
                setActiveRun((prev) => ({
                  ...prev,
                  status: 'waiting_input',
                  pendingConfirmation: null,
                  finalContent: '',
                }));
                finalContent = '';
                addStep(type as RunStepType, data);
                continue;
              }

              if (type === 'run_paused') {
                const reason = String((data.reason as string) ?? '').trim();
                const isPaused = reason === 'waiting_confirmation' || reason === 'waiting_input';
                setActiveRun((prev) => ({
                  ...prev,
                  status:
                    reason === 'waiting_confirmation'
                      ? 'waiting_confirmation'
                      : reason === 'waiting_input'
                        ? 'waiting_input'
                        : prev.status,
                  finalContent: isPaused ? '' : prev.finalContent,
                }));
                if (isPaused) finalContent = '';
                continue;
              }

              if (type === 'stop') {
                const reason = String((data.reason as string) ?? '').trim();
                const isPaused = reason === 'waiting_confirmation' || reason === 'waiting_input';
                if (isPaused) {
                  setActiveRun((prev) => ({
                    ...prev,
                    status: reason as ActiveRun['status'],
                    finalContent: '',
                  }));
                  finalContent = '';
                } else {
                  setActiveRun((prev) => ({ ...prev, status: reason as ActiveRun['status'] }));
                }
                if (!isPaused) addStep(type as RunStepType, data);
                continue;
              }

              addStep(type as RunStepType, data);
            } catch {
              // ignore parse errors
            }
          }
        }

        setActiveRun((prev) => ({
          ...prev,
          status: prev.status === 'waiting_confirmation' || prev.status === 'waiting_input'
            ? prev.status
            : 'completed',
          finalContent,
        }));
      } catch (err: unknown) {
        if ((err as Error).name === 'AbortError') return;
        const message = err instanceof Error ? err.message : String(err);
        addStep('error', { error: message });
        setActiveRun((prev) => ({ ...prev, status: 'error' }));
      } finally {
        // Invalidate runs list to show new run
        qc.invalidateQueries({ queryKey: qk.sandbox.runs.list(sessionId) });
        if (branchId) {
          qc.invalidateQueries({ queryKey: qk.sandbox.runs.list(sessionId, branchId) });
        }
        qc.invalidateQueries({
          queryKey: qk.sandbox.sessions.detail(sessionId),
        });
      }
    },
    [sessionId, addStep, qc],
  );

  const confirmAction = useCallback(
    async (confirmed: boolean, userInput?: string) => {
      if (!activeRun.runId) return;
      try {
        if (!confirmed) {
          // Just cancel without streaming
          await sandboxApi.confirmRunAction(sessionId, activeRun.runId, {
            confirmed: false,
          });
          setActiveRun((prev) => ({
            ...prev,
            status: 'completed',
            pendingConfirmation: null,
          }));
          addStep('status', { stage: 'write_rejected' });
          return;
        }

        // For confirm, use resume endpoint with SSE streaming
        const controller = new AbortController();
        abortRef.current = controller;

        const response = await sandboxApi.resumeRun(
          sessionId,
          activeRun.runId,
          { confirmed: true, user_input: userInput },
          controller.signal,
        );

        if (!response.ok) {
          const err = await response.text();
          throw new Error(err || `HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalContent = '';
        let isDone = false;

        setActiveRun((prev) => ({
          ...prev,
          status: 'running',
          pendingConfirmation: null,
        }));
        addStep('status', { stage: 'write_confirmed' });

        while (reader && !isDone) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;
            if (raw === '[DONE]') {
              isDone = true;
              break;
            }
            try {
              const event = JSON.parse(raw) as SandboxSSEEvent;
              const { type, run_id, ...data } = event;

              if (type === 'chunk' && typeof data.text === 'string') {
                finalContent += data.text;
                setActiveRun((prev) => ({ ...prev, finalContent }));
              }

              if (type === 'delta') {
                finalContent += (data.content as string) ?? '';
                setActiveRun((prev) => ({ ...prev, finalContent }));
              }

              if (type === 'final' || type === 'final_content') {
                finalContent = (data.content as string) ?? finalContent;
                setActiveRun((prev) => ({ ...prev, finalContent }));
              }

              if (type === 'run_paused') {
                const reason = String((data.reason as string) ?? '').trim();
                setActiveRun((prev) => ({
                  ...prev,
                  status: reason === 'waiting_confirmation' ? 'waiting_confirmation' : 'waiting_input',
                  pendingConfirmation: event,
                }));
                continue;
              }

              if (type === 'confirmation_required') {
                setActiveRun((prev) => ({
                  ...prev,
                  status: 'waiting_confirmation',
                  pendingConfirmation: event,
                  finalContent: '',
                }));
                finalContent = '';
                addStep(type as RunStepType, data);
                continue;
              }

              if (type === 'waiting_input') {
                setActiveRun((prev) => ({
                  ...prev,
                  status: 'waiting_input',
                  pendingConfirmation: null,
                  finalContent: '',
                }));
                finalContent = '';
                addStep(type as RunStepType, data);
                continue;
              }

              if (type === 'run_paused') {
                const reason = String((event.reason as string) ?? '').trim();
                if (reason === 'waiting_confirmation' || reason === 'waiting_input') {
                  setActiveRun((prev) => ({
                    ...prev,
                    status: reason as ActiveRun['status'],
                    finalContent: '',
                  }));
                  finalContent = '';
                }
                continue;
              }

              if (type === 'error') {
                const errorMsg = String((data.error as string) ?? 'Unknown error');
                throw new Error(errorMsg);
              }

              if (type === 'done') {
                isDone = true;
              }

              addStep(type as RunStepType, data);
            } catch {
              // Ignore malformed events
            }
          }
        }

        setActiveRun((prev) => ({
          ...prev,
          status: prev.status === 'waiting_confirmation' || prev.status === 'waiting_input'
            ? prev.status
            : 'completed',
          finalContent,
        }));
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        addStep('error', { error: `Resume failed: ${message}` });
        setActiveRun((prev) => ({
          ...prev,
          status: 'error',
          pendingConfirmation: null,
        }));
      }
    },
    [sessionId, activeRun.runId, addStep],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setActiveRun((prev) => ({
      ...prev,
      status: prev.status === 'running' ? 'completed' : prev.status,
    }));
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setActiveRun(INITIAL_RUN);
  }, []);

  return {
    activeRun,
    runs: activeRun.runId
      ? [
          {
            id: activeRun.runId,
            requestText: activeRun.requestText,
            startedAt: activeRun.startedAt,
            status: activeRun.status,
            steps: activeRun.steps,
            finalContent: activeRun.finalContent,
          } satisfies SandboxRun,
        ]
      : [],
    activeRunId: activeRun.runId,
    setActiveRunId: (_id: string | null) => {},
    isRunning: activeRun.status === 'running',
    isWaitingConfirmation: activeRun.status === 'waiting_confirmation' && activeRun.pendingConfirmation !== null,
    isWaitingInput: activeRun.status === 'waiting_input',
    run,
    stop,
    reset,
    confirmAction,
  };
}
