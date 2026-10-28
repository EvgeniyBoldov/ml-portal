import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { consumeSse } from '@/shared/api/sse';
import { fetchChatStatusEvents } from '@/shared/api/chats';
import type {
  ChatExecutionStage,
  ChatLifecycleStatus,
  ChatStatusSnapshot,
} from '@/shared/api/chats';
import { qk } from '@/shared/api/keys';
import { useAuth } from '@/shared/hooks/useAuth';
import { useToast } from '@/shared/ui/Toast';

const statuses = new Set<ChatLifecycleStatus>([
  'running',
  'waiting_input',
  'waiting_confirmation',
  'completed',
  'failed',
  'cancelled',
]);
const stages = new Set<ChatExecutionStage>([
  'preparing',
  'planning',
  'executing',
  'synthesizing',
  'finalizing',
]);

export function parseChatStatusSnapshot(data: string): ChatStatusSnapshot[] | null {
  try {
    const parsed: unknown = JSON.parse(data);
    if (!Array.isArray(parsed)) return null;
    const result: ChatStatusSnapshot[] = [];
    for (const value of parsed) {
      if (!value || typeof value !== 'object') return null;
      const item = value as Record<string, unknown>;
      if (
        typeof item.chat_id !== 'string' ||
        !statuses.has(item.status as ChatLifecycleStatus) ||
        (item.run_id !== null && typeof item.run_id !== 'string')
      ) return null;
      result.push({
        chat_id: item.chat_id,
        run_id: item.run_id as string | null,
        status: item.status as ChatLifecycleStatus,
        stage: stages.has(item.stage as ChatExecutionStage)
          ? item.stage as ChatExecutionStage
          : null,
        updated_at: typeof item.updated_at === 'string' ? item.updated_at : null,
        stage_updated_at: typeof item.stage_updated_at === 'string'
          ? item.stage_updated_at
          : null,
      });
    }
    return result;
  } catch {
    return null;
  }
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise(resolve => {
    if (signal.aborted) return resolve();
    let timer: number | undefined;
    const finish = () => {
      if (timer !== undefined) window.clearTimeout(timer);
      signal.removeEventListener('abort', finish);
      resolve();
    };
    timer = window.setTimeout(finish, ms);
    signal.addEventListener('abort', finish, { once: true });
    if (signal.aborted) finish();
  });
}

function notifyCompletedTransitions(
  previous: ChatStatusSnapshot[] | undefined,
  next: ChatStatusSnapshot[],
  notify: (item: ChatStatusSnapshot) => void
) {
  if (!previous) return;
  const previousByChat = new Map(previous.map(item => [item.chat_id, item]));
  for (const current of next) {
    if (current.status !== 'completed') continue;
    const before = previousByChat.get(current.chat_id);
    if (
      before &&
      (before.status === 'running' || before.status === 'waiting_input' ||
        before.status === 'waiting_confirmation' || before.run_id !== current.run_id)
    ) notify(current);
  }
}

/** Maintains a user-scoped status cache and notifies when a turn completes. */
export function GlobalChatStatusListener() {
  const { user, isAuthReady } = useAuth();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const userId = user?.id;

  useEffect(() => {
    if (!isAuthReady || !userId) return;
    const controller = new AbortController();
    const queryKey = qk.chats.statuses(userId);
    let previous = queryClient.getQueryData<ChatStatusSnapshot[]>(queryKey);
    let retryMs = 1000;
    const notifiedRunIds = new Set<string>();

    void (async () => {
      while (!controller.signal.aborted) {
        try {
          const response = await fetchChatStatusEvents(controller.signal);
          if (!response.ok) throw new Error(`Chat status stream returned ${response.status}`);
          await consumeSse(response, ({ event, data }) => {
            if (event !== 'snapshot') return;
            const snapshot = parseChatStatusSnapshot(data);
            if (!snapshot) return;
            notifyCompletedTransitions(previous, snapshot, item => {
              const notificationKey = `${item.chat_id}:${item.run_id || 'unknown'}`;
              if (notifiedRunIds.has(notificationKey)) return;
              notifiedRunIds.add(notificationKey);
              showToast('Ответ в одном из чатов готов', 'success');
            });
            previous = snapshot;
            queryClient.setQueryData(queryKey, snapshot);
          });
          retryMs = 1000;
        } catch (error) {
          if (controller.signal.aborted) break;
          console.warn('Global chat status stream disconnected', error);
        }
        await delay(retryMs, controller.signal);
        retryMs = Math.min(retryMs * 2, 30000);
      }
    })();

    return () => {
      controller.abort();
      queryClient.removeQueries({ queryKey });
    };
  }, [isAuthReady, queryClient, showToast, userId]);

  return null;
}

