import { consumeSse } from '@/shared/api/sse';
import { idempotencyKey } from '@/shared/lib/idempotency';
import type { ChatRuntimeProgress } from './types';

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
}

export type ChatStreamEvent =
  | { type: 'user_message'; messageId: string; createdAt?: string }
  | { type: 'delta'; content: string }
  | { type: 'final'; final: ChatStreamFinal }
  | { type: 'status'; progress: ChatRuntimeProgress }
  | { type: 'pause'; pause: ChatStreamPause }
  | { type: 'cached' };

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function progressFrom(value: unknown): ChatRuntimeProgress | null {
  const raw = record(value);
  const description =
    typeof raw.description === 'string' ? raw.description.trim() : '';
  if (!description) return null;
  return {
    id: idempotencyKey(),
    runId: typeof raw.run_id === 'string' ? raw.run_id : '',
    phase: typeof raw.phase === 'string' ? raw.phase : '',
    kind: typeof raw.kind === 'string' ? raw.kind : '',
    description,
    status: typeof raw.status === 'string' ? raw.status : undefined,
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
    last.kind === progress.kind &&
    last.phase === progress.phase &&
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
  let terminal: 'final' | 'pause' | 'cached' | null = null;
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
      !['user_message', 'status', 'final', 'pause', 'cached', 'error'].includes(
        event
      )
    )
      return;
    let payload: Record<string, unknown>;
    try {
      payload = record(JSON.parse(data));
    } catch {
      if (event === 'status') return;
      throw new Error(`Некорректное событие чата: ${event}`);
    }
    if (event === 'user_message') {
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
    } else if (event === 'status') {
      if (payload.stage !== 'runtime_progress') return;
      const progress = progressFrom(payload.progress);
      if (progress) await onEvent({ type: 'status', progress });
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
      throw new Error(
        typeof payload.code === 'string' && payload.code
          ? `${payload.code}: ${message}`
          : message
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
