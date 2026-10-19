import {
  useCallback,
  useEffect,
  useRef,
  type Dispatch,
  type SetStateAction,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toApiError } from '@/shared/api/errors';
import { qk } from '@/shared/api/keys';
import { fetchStreamWithAuth } from '@/shared/api/streamAuth';
import { generateChatTitle, resumeRunStream } from '@/shared/api/chats';
import { idempotencyKey as createIdempotencyKey } from '@/shared/lib/idempotency';
import { toAttachments, toRagSources } from '../chatMessages';
import {
  appendRuntimeProgress,
  consumeChatStream,
  type ChatStreamPause,
} from '../chatStream';
import type { ActiveChatRun, ChatTimelineMessage } from '../types';

type MessagesByChat = Record<
  string,
  { items: ChatTimelineMessage[]; loading: boolean; loaded?: boolean }
>;
interface Options {
  pausedInteractionId: string | null;
  hasInteraction: boolean;
  activeRun: ActiveChatRun | null;
  setActiveRun: Dispatch<SetStateAction<ActiveChatRun | null>>;
  setMessagesByChat: Dispatch<SetStateAction<MessagesByChat>>;
  setIsStreaming: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  clearPendingState: () => void;
  clearPausedInteraction: () => void;
  applyPausedState: (pause: ChatStreamPause) => void;
  loadMessages: (chatId: string) => Promise<void>;
  invalidateHistory: (chatId: string) => void;
}

async function ensureResponse(response: Response) {
  if (response.ok && response.body) return;
  throw await toApiError(response);
}

export function useChatStreaming({
  activeRun,
  pausedInteractionId,
  hasInteraction,
  setActiveRun,
  setMessagesByChat,
  setIsStreaming,
  setError,
  clearPendingState,
  clearPausedInteraction,
  applyPausedState,
  loadMessages,
  invalidateHistory,
}: Options) {
  const controllerRef = useRef<AbortController | null>(null);
  const flushRef = useRef<(() => void) | null>(null);
  const currentChatRef = useRef<string | null>(null);
  const queryClient = useQueryClient();
  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    []
  );

  const abortStream = useCallback(() => {
    flushRef.current?.();
    controllerRef.current?.abort();
    controllerRef.current = null;
    setIsStreaming(false);
    clearPendingState();
  }, [clearPendingState, setIsStreaming]);

  const setCurrentChat = useCallback(
    (chatId: string) => {
      if (currentChatRef.current !== chatId) abortStream();
      currentChatRef.current = chatId;
    },
    [abortStream]
  );

  const updateMessage = useCallback(
    (chatId: string, id: string, patch: Partial<ChatTimelineMessage>) => {
      setMessagesByChat(prev => {
        const current = prev[chatId];
        if (!current) return prev;
        return {
          ...prev,
          [chatId]: {
            ...current,
            items: current.items.map(item =>
              item.id === id ? { ...item, ...patch } : item
            ),
          },
        };
      });
    },
    [setMessagesByChat]
  );

  const addMessages = useCallback(
    (chatId: string, items: ChatTimelineMessage[]) => {
      setMessagesByChat(prev => {
        const current = prev[chatId] || {
          items: [],
          loading: false,
          loaded: true,
        };
        return {
          ...prev,
          [chatId]: {
            ...current,
            loaded: true,
            items: [...current.items, ...items],
          },
        };
      });
    },
    [setMessagesByChat]
  );

  const removeEmptyAssistant = useCallback(
    (chatId: string, id: string) => {
      setMessagesByChat(prev => {
        const current = prev[chatId];
        if (!current) return prev;
        return {
          ...prev,
          [chatId]: {
            ...current,
            items: current.items.filter(
              item => !(item.id === id && item.isOptimistic && !item.content)
            ),
          },
        };
      });
    },
    [setMessagesByChat]
  );

  const refreshTitle = useCallback(
    (chatId: string) => {
      void generateChatTitle(chatId)
        .then(result => {
          if (!result.generated || !result.title) return;
          queryClient.setQueriesData(
            { queryKey: qk.chats.all() },
            (oldData: unknown) => {
              if (!oldData || typeof oldData !== 'object') return oldData;
              const typed = oldData as {
                items?: Array<Record<string, unknown>>;
              };
              if (!Array.isArray(typed.items)) return oldData;
              return {
                ...typed,
                items: typed.items.map(chat =>
                  chat.id === chatId ? { ...chat, name: result.title } : chat
                ),
              };
            }
          );
        })
        .catch(() => undefined);
    },
    [queryClient]
  );

  const receiveStream = useCallback(
    async (
      response: Response,
      chatId: string,
      assistantId: string,
      userId: string | null,
      controller: AbortController,
      onChunk: (content: string) => void,
      allowDoneOnly = false
    ) => {
      let currentAssistantId = assistantId;
      let renderedContent: string | null = null;
      let timer: ReturnType<typeof setTimeout> | null = null;
      const isCurrent = () => controllerRef.current === controller;
      const flush = () => {
        if (isCurrent() && renderedContent !== null)
          updateMessage(chatId, currentAssistantId, {
            content: renderedContent,
          });
      };
      flushRef.current = flush;
      try {
        return await consumeChatStream(
          response,
          async event => {
            if (!isCurrent()) return;
            if (event.type === 'delta') {
              renderedContent = event.content;
              if (!timer)
                timer = setTimeout(() => {
                  timer = null;
                  flush();
                }, 40);
              onChunk(event.content);
            } else if (event.type === 'final') {
              if (timer) {
                clearTimeout(timer);
                timer = null;
              }
              renderedContent = event.final.content;
              updateMessage(chatId, currentAssistantId, {
                id: event.final.messageId,
                content: event.final.content,
                isOptimistic: false,
                ...(event.final.createdAt
                  ? { createdAt: event.final.createdAt }
                  : {}),
                meta: {
                  attachments: toAttachments(event.final.attachments),
                  ragSources: toRagSources(event.final.sources),
                },
              });
              currentAssistantId = event.final.messageId;
              setActiveRun(current =>
                current
                  ? { ...current, assistantMessageId: currentAssistantId }
                  : current
              );
              onChunk(event.final.content);
              refreshTitle(chatId);
            } else if (event.type === 'user_message' && userId) {
              updateMessage(chatId, userId, {
                id: event.messageId,
                isOptimistic: false,
                ...(event.createdAt ? { createdAt: event.createdAt } : {}),
              });
              setActiveRun(current =>
                current
                  ? { ...current, userMessageId: event.messageId }
                  : current
              );
            } else if (event.type === 'status') {
              setActiveRun(current =>
                current
                  ? {
                      ...current,
                      runId: event.progress.runId || current.runId,
                      progress: appendRuntimeProgress(
                        current.progress,
                        event.progress
                      ),
                    }
                  : current
              );
            } else if (event.type === 'pause') {
              applyPausedState(event.pause);
            } else if (event.type === 'cached') {
              await loadMessages(chatId);
            }
          },
          { allowDoneOnly }
        );
      } finally {
        if (timer) clearTimeout(timer);
        // Keep the last received text even if EOF/error beats the render timer.
        flush();
        if (flushRef.current === flush) flushRef.current = null;
      }
    },
    [applyPausedState, loadMessages, refreshTitle, setActiveRun, updateMessage]
  );

  const executeStream = useCallback(
    async (
      chatId: string,
      assistantId: string,
      userId: string | null,
      controller: AbortController,
      request: () => Promise<Response>,
      onChunk: (content: string) => void,
      onError: (message: string) => void,
      allowDoneOnly = false,
      previousRun?: ActiveChatRun | null
    ) => {
      let hasOpenedStream = false;
      try {
        const response = await request();
        await ensureResponse(response);
        if (controllerRef.current !== controller) return false;
        hasOpenedStream = true;
        const terminal = await receiveStream(
          response,
          chatId,
          assistantId,
          userId,
          controller,
          onChunk,
          allowDoneOnly
        );
        if (controllerRef.current !== controller) return false;
        if (terminal !== 'pause') clearPendingState();
        if (allowDoneOnly) removeEmptyAssistant(chatId, assistantId);
        return true;
      } catch (error: unknown) {
        if (controllerRef.current !== controller) return false;
        if (previousRun !== undefined && !hasOpenedStream) {
          // A rejected continuation leaves the existing pause available to retry.
          setActiveRun(previousRun);
          if (!previousRun) removeEmptyAssistant(chatId, assistantId);
        } else {
          clearPendingState();
          removeEmptyAssistant(chatId, assistantId);
        }
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          const message =
            error instanceof Error ? error.message : 'Ошибка получения ответа';
          setError(message);
          onError(message);
        }
        return false;
      } finally {
        if (controllerRef.current === controller) {
          controllerRef.current = null;
          setIsStreaming(false);
        }
      }
    },
    [
      clearPendingState,
      receiveStream,
      removeEmptyAssistant,
      setActiveRun,
      setError,
      setIsStreaming,
    ]
  );

  const sendMessageStream = useCallback(
    async (
      chatId: string,
      message: string,
      useRag: boolean,
      onChunk: (content: string) => void,
      onError: (message: string) => void,
      agentSlug?: string,
      artifactIds?: string[],
      attachmentMeta?: unknown[],
      confirmationTokens?: string[]
    ) => {
      if (controllerRef.current) {
        onError('Дождитесь завершения текущего ответа');
        return false;
      }
      currentChatRef.current = chatId;
      const controller = new AbortController();
      controllerRef.current = controller;
      clearPendingState();
      setError(null);
      setIsStreaming(true);
      invalidateHistory(chatId);
      const userId = `temp-user-${createIdempotencyKey()}`;
      const assistantId = `temp-assistant-${createIdempotencyKey()}`;
      const createdAt = new Date().toISOString();
      addMessages(chatId, [
        {
          id: userId,
          role: 'user',
          content: message,
          createdAt,
          isOptimistic: true,
          meta: attachmentMeta?.length
            ? { attachments: toAttachments(attachmentMeta) }
            : undefined,
        },
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          createdAt,
          isOptimistic: true,
        },
      ]);
      setActiveRun({
        userMessageId: userId,
        assistantMessageId: assistantId,
        progress: [],
        status: 'running',
      });
      const idempotencyKey = createIdempotencyKey();
      return executeStream(
        chatId,
        assistantId,
        userId,
        controller,
        () =>
          fetchStreamWithAuth(`/chats/${chatId}/messages`, {
            signal: controller.signal,
            idempotencyKey,
            body: {
              content: message,
              use_rag: useRag,
              agent_slug: agentSlug,
              execution_mode: 'normal',
              artifact_ids: artifactIds ?? [],
              confirmation_tokens: confirmationTokens ?? [],
            },
          }),
        onChunk,
        onError
      );
    },
    [
      addMessages,
      clearPendingState,
      executeStream,
      invalidateHistory,
      setActiveRun,
      setError,
      setIsStreaming,
    ]
  );

  const resumeStream = useCallback(
    async (
      runId: string,
      action: 'confirm' | 'cancel' | 'input' | 'answer',
      input: string | boolean,
      onChunk: (content: string) => void,
      onError: (message: string) => void
    ) => {
      const chatId = currentChatRef.current;
      if (!runId || !chatId) {
        onError('Не выбран чат или запуск для продолжения');
        return false;
      }
      if (controllerRef.current) {
        onError('Дождитесь завершения текущего ответа');
        return false;
      }
      const controller = new AbortController();
      controllerRef.current = controller;
      setError(null);
      setIsStreaming(true);
      invalidateHistory(chatId);
      const assistantId =
        activeRun?.assistantMessageId ||
        `temp-assistant-${createIdempotencyKey()}`;
      if (action !== 'cancel' && !activeRun) {
        addMessages(chatId, [
          {
            id: assistantId,
            role: 'assistant',
            content: '',
            createdAt: new Date().toISOString(),
            isOptimistic: true,
          },
        ]);
      }
      setActiveRun({
        userMessageId: activeRun?.userMessageId || '',
        assistantMessageId: assistantId,
        runId,
        progress: activeRun?.progress || [],
        status: 'running',
      });
      return executeStream(
        chatId,
        assistantId,
        null,
        controller,
        async () => {
          const response = await resumeRunStream(
            runId,
            action,
            input,
            controller.signal,
            pausedInteractionId,
            hasInteraction
          );
          if (
            response.ok &&
            response.body &&
            controllerRef.current === controller
          )
            clearPausedInteraction();
          return response;
        },
        onChunk,
        onError,
        action === 'cancel',
        activeRun
      );
    },
    [
      activeRun,
      pausedInteractionId,
      hasInteraction,
      addMessages,
      clearPausedInteraction,
      executeStream,
      invalidateHistory,
      setActiveRun,
      setError,
      setIsStreaming,
    ]
  );

  return { abortStream, setCurrentChat, sendMessageStream, resumeStream };
}
