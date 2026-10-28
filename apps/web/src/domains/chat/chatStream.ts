import { consumeSse } from '@/shared/api/sse';
import { idempotencyKey } from '@/shared/lib/idempotency';
import type { ChatLifecycleStatus, ChatRuntimeProgress } from './types';

export interface ChatStreamPause {
  runId: string;
  reason: 'waiting_confirmation' | 'waiting_input';
  question?: string;
  message?: string;
  action: Record<string, unknown>;
  interaction?: Record<string, unknown>;
}

export interface ChatStreamFinal {
  messageId: string;
  content: string;
  createdAt?: string;
  sources: unknown;
  attachments: unknown;
  stopReason?: string;
  status: ChatLifecycleStatus;
}

export type ChatStreamEvent =
  | { type: 'run_started'; runId: string; status: ChatLifecycleStatus }
  | {
      type: 'state';
      runId: string;
      status: ChatLifecycleStatus;
      stage?: ChatRuntimeProgress['stage'];
      activity?: ChatRuntimeProgress;
      pauseReason?: string;
    }
  | { type: 'cancelled'; runId: string }
  | { type: 'user_message'; messageId: string; createdAt?: string }
  | { type: 'delta'; content: string }
  | { type: 'final'; final: ChatStreamFinal }
  | { type: 'stage'; activity: ChatRuntimeProgress }
  | { type: 'pause'; pause: ChatStreamPause }
  | { type: 'cached' };

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

const lifecycleStatuses = new Set<ChatLifecycleStatus>([
  'running', 'waiting_input', 'waiting_confirmation', 'completed', 'failed', 'cancelled',
]);
const executionStages = new Set<ChatRuntimeProgress['stage']>([
  'preparing', 'planning', 'executing', 'synthesizing', 'finalizing',
]);

function progressFrom(value: unknown): ChatRuntimeProgress | null {
  const raw = record(value);
  const description =
    typeof raw.description === 'string' ? raw.description.trim() : '';
  if (!description) return null;
  return {
    id: idempotencyKey(),
    runId: typeof raw.run_id === 'string' ? raw.run_id : '',
    stage: executionStages.has(raw.stage as ChatRuntimeProgress['stage'])
      ? (raw.stage as ChatRuntimeProgress['stage'])
      : 'preparing',
    action: typeof raw.action === 'string' ? raw.action : 'runtime_activity',
    description,
    outcome: typeof raw.outcome === 'string' ? raw.outcome : undefined,
    createdAt: new Date().toISOString(),
  };
}

export function appendRuntimeProgress(
  current: ChatRuntimeProgress[],
  progress: ChatRuntimeProgress
) {
  const last = current.at(-1);
  if (
    last?.description === progress.description &&
    last.action === progress.action &&
    last.stage === progress.stage &&
    last.runId === progress.runId
  ) {
    // A repeated title can carry a new explicit outcome. Do not drop it.
    return [...current.slice(0, -1), { ...progress, id: last.id }];
  }
  return [...current, progress].slice(-10);
}

/** One answer lifecycle for initial sends and HITL continuations. */
export async function consumeChatStream(
  response: Response,
  onEvent: (event: ChatStreamEvent) => void | Promise<void>,
  { allowDoneOnly = false }: { allowDoneOnly?: boolean } = {}
) {
  let content = '';
  let terminal: 'final' | 'pause' | 'cached' | 'cancelled' | null = null;
  let hasReceivedDone = false;
  await consumeSse(response, async ({ event, data }) => {
    if (event === 'done' || data === '[DONE]') {
      hasReceivedDone = true;
      return false;
    }
    if (event === 'delta') {
      content += data;
      await onEvent({ type: 'delta', content });
      return;
    }
    if (
      !['state', 'stage', 'status', 'run_started', 'cancelled', 'user_message', 'final', 'pause', 'cached', 'error'].includes(
        event
      )
    )
      return;
    let payload: Record<string, unknown>;
    try {
      payload = record(JSON.parse(data));
    } catch {
      // Older workers sometimes emitted malformed generic status frames.
      // Ignore those during rolling upgrades; the typed contract events remain strict.
      if (event === 'status') return;
      throw new Error(`Некорректное событие чата: ${event}`);
    }
    if (event === 'state') {
      if (typeof payload.run_id === 'string' && lifecycleStatuses.has(payload.status as ChatLifecycleStatus)) {
        const activity = progressFrom(payload.activity);
        await onEvent({
          type: 'state',
          runId: payload.run_id,
          status: payload.status as ChatLifecycleStatus,
          stage: executionStages.has(payload.stage as ChatRuntimeProgress['stage'])
            ? payload.stage as ChatRuntimeProgress['stage']
            : activity?.stage,
          activity: activity || undefined,
          pauseReason: typeof payload.pause_reason === 'string' ? payload.pause_reason : undefined,
        });
      }
    } else if (event === 'stage') {
      const activity = progressFrom(payload.activity);
      if (activity) await onEvent({ type: 'stage', activity });
    } else if (event === 'status') {
      // Compatibility with older API workers during rolling deployment.
      if (payload.stage === 'runtime_progress') {
        const old = record(payload.progress);
        const activity = progressFrom({
          run_id: old.run_id,
          stage: old.phase === 'planner' || old.phase === 'preflight' ? 'planning'
            : old.phase === 'agent' || old.phase === 'execution' ? 'executing'
              : old.phase === 'synthesis' ? 'synthesizing' : 'preparing',
          action: old.kind,
          description: old.description,
          outcome: old.status,
        });
        if (activity) await onEvent({ type: 'stage', activity });
      }
    } else if (event === 'run_started') {
      if (typeof payload.run_id === 'string' && lifecycleStatuses.has((payload.status || 'running') as ChatLifecycleStatus))
        await onEvent({
          type: 'run_started', runId: payload.run_id,
          status: (payload.status || 'running') as ChatLifecycleStatus,
        });
    } else if (event === 'cancelled') {
      if (typeof payload.run_id === 'string') {
        terminal = 'cancelled';
        await onEvent({ type: 'cancelled', runId: payload.run_id });
      }
    } else if (event === 'user_message') {
      if (typeof payload.message_id !== 'string')
        throw new Error('В событии отсутствует ID сообщения');
      await onEvent({
        type: 'user_message',
        messageId: payload.message_id,
        createdAt:
          typeof payload.created_at === 'string'
            ? payload.created_at
            : undefined,
      });
    } else if (event === 'final') {
      if (typeof payload.message_id !== 'string')
        throw new Error('В ответе отсутствует ID сообщения');
      content = typeof payload.content === 'string' ? payload.content : content;
      terminal = 'final';
      await onEvent({
        type: 'final',
        final: {
          messageId: payload.message_id,
          content,
          createdAt:
            typeof payload.created_at === 'string'
              ? payload.created_at
              : undefined,
          sources: payload.sources,
          attachments: payload.attachments,
          stopReason:
            typeof payload.stop_reason === 'string'
              ? payload.stop_reason
              : undefined,
          status: lifecycleStatuses.has(payload.status as ChatLifecycleStatus)
            ? payload.status as ChatLifecycleStatus
            : (payload.stop_reason === 'failed' ? 'failed' : 'completed'),
        },
      });
    } else if (event === 'pause') {
      if (
        (payload.reason !== 'waiting_input' &&
          payload.reason !== 'waiting_confirmation') ||
        typeof payload.run_id !== 'string'
      ) {
        throw new Error('Некорректное событие паузы');
      }
      const context = record(payload.context);
      terminal = 'pause';
      await onEvent({
        type: 'pause',
        pause: {
          runId: payload.run_id,
          reason: payload.reason,
          action: record(payload.action),
          interaction:
            typeof record(context.interaction).id === 'string'
              ? record(context.interaction)
              : undefined,
          question:
            typeof context.question === 'string' ? context.question : undefined,
          message:
            typeof context.message === 'string' ? context.message : undefined,
        },
      });
    } else if (event === 'cached') {
      terminal = 'cached';
      await onEvent({ type: 'cached' });
    } else if (event === 'error') {
      const message =
        typeof payload.error === 'string' ? payload.error : 'Ошибка выполнения';
      throw new ChatStreamFailure(
        typeof payload.code === 'string' && payload.code
          ? `${payload.code}: ${message}`
          : message,
        typeof payload.code === 'string' ? payload.code : undefined,
      );
    }
    if (terminal) return false;
  });
  if (!terminal && !(allowDoneOnly && hasReceivedDone)) {
    throw new Error(
      'Соединение прервалось до завершения ответа. Полученный текст сохранён на экране.'
    );
  }
  return terminal;
}

export class ChatStreamFailure extends Error {
  constructor(message: string, readonly code?: string) {
    super(message);
    this.name = 'ChatStreamFailure';
  }
}
