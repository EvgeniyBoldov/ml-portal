/**
 * Hook for sandbox run execution via SSE streaming.
 * Session-first: runs are scoped to a sandbox session.
 */
import { useState, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { sandboxApi } from '../api';
import type { SandboxSSEEvent, SandboxRunCreate } from '../types';

export type RunStepType =
  | 'status'
  | 'thinking'
  | 'tool_call'
  | 'tool_result'
  | 'delta'
  | 'final'
  | 'final_content'
  | 'error'
  | 'routing'
  | 'planner_action'
  | 'policy_decision'
  | 'confirmation_required'
  | 'waiting_input'
  | 'stop'
  | 'done';

export interface RunStep {
  id: string;
  type: RunStepType;
  data: Record<string, unknown>;
  timestamp: number;
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
  const qc = useQueryClient();

  const addStep = useCallback(
    (type: RunStepType, data: Record<string, unknown>) => {
      const step: RunStep = {
        id: crypto.randomUUID(),
        type,
        data,
        timestamp: Date.now(),
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
      attachmentIds?: string[]
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

      const controller = new AbortController();
      abortRef.current = controller;

      const body: SandboxRunCreate = {
        request_text: requestText,
        branch_id: branchId ?? undefined,
        parent_run_id: parentRunId ?? undefined,
        attachment_ids: attachmentIds?.length ? attachmentIds : undefined,
      };

      try {
        const url = sandboxApi.getRunStreamUrl(sessionId);
        const headers = sandboxApi.getRunStreamHeaders();

        const response = await fetch(url, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
          signal: controller.signal,
          credentials: 'include',
        });

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
                }));
                addStep(type as RunStepType, data);
                continue;
              }

              if (type === 'waiting_input') {
                setActiveRun((prev) => ({
                  ...prev,
                  status: 'waiting_input',
                  pendingConfirmation: null,
                }));
                addStep(type as RunStepType, data);
                continue;
              }

              if (type === 'stop') {
                addStep(type as RunStepType, data);
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
    async (confirmed: boolean) => {
      if (!activeRun.runId) return;
      try {
        await sandboxApi.confirmRunAction(sessionId, activeRun.runId, {
          confirmed,
        });
        setActiveRun((prev) => ({
          ...prev,
          status: confirmed ? 'running' : 'completed',
          pendingConfirmation: null,
        }));
        addStep('status', {
          stage: confirmed ? 'write_confirmed' : 'write_rejected',
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        addStep('error', { error: `Confirmation failed: ${message}` });
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
