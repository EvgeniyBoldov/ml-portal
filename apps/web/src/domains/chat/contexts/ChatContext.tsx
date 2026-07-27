import React, { createContext, useContext, useState, useCallback, useRef, ReactNode, useMemo } from 'react';
import { useChats } from '@shared/api/hooks/useChats';
import { useQueryClient } from '@tanstack/react-query';
import type { Chat, ChatMessage } from '@shared/api/types';
import { qk } from '@/shared/api/keys';
import { consumeSse } from '@/shared/api/sse';
import type { ActiveChatRun, ChatAttachmentRef, ChatMessageMeta, ChatRagSource, ChatRuntimeProgress, ChatTimelineMessage } from '../types';

type Message = ChatTimelineMessage;

interface PendingConfirmation {
  operationFingerprint: string;
  toolSlug: string;
  operation: string;
  riskLevel: string;
  argsPreview: string;
  summary: string;
  runId?: string | null;
}

interface PendingInput {
  question?: string;
  reason?: string;
}

interface ResumePausedState {
  runId?: string | null;
  reason?: string | null;
  question?: string | null;
  message?: string | null;
  action?: Record<string, unknown> | null;
}

interface ChatState {
  chatsOrder: string[];
  chatsById: Record<string, Chat>;
  messagesByChat: Record<string, { items: Message[]; loading: boolean; loaded?: boolean }>;
  error: string | null;
  isLoading: boolean;
  activeRun: ActiveChatRun | null;
  pendingConfirmations: PendingConfirmation[];
  pendingConfirmationTokens: string[];
  pendingInput: PendingInput | null;
  stopReason: string | null;
  pausedRunId: string | null;
  isStreaming: boolean;
}

interface ChatActions {
  loadMessages: (chatId: string) => Promise<void>;
  setCurrentChat: (chatId: string) => void;
  clearPendingState: () => void;
  applyPausedState: (state: ResumePausedState) => void;
  abortStream: () => void;
  sendMessageStream: (
    chatId: string,
    message: string,
    useRag: boolean,
    onChunk: (chunk: string) => void,
    onError: (error: string) => void,
    agentSlug?: string,
    attachmentIds?: string[],
    attachmentMeta?: unknown[],
    confirmationTokens?: string[]
  ) => Promise<void>;
  resumeStream: (
    runId: string,
    action: 'confirm' | 'cancel' | 'input',
    input: string,
    onChunk: (chunk: string) => void,
    onError: (error: string) => void,
  ) => Promise<void>;
}

const ChatActionsContext = createContext<ChatActions | null>(null);
const ChatMessagesStateContext = createContext<
  Pick<
    ChatState,
    | "messagesByChat"
    | "activeRun"
    | "pendingConfirmations"
    | "pendingInput"
    | "pausedRunId"
    | "isStreaming"
    | "isLoading"
  > | null
>(null);
const ChatCatalogStateContext = createContext<
  Pick<ChatState, "chatsOrder" | "chatsById" | "messagesByChat"> | null
>(null);

function toAttachments(value: unknown): ChatAttachmentRef[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const raw = item as Record<string, unknown>;
    const artifactId = typeof raw.artifact_id === 'string' ? raw.artifact_id : '';
    const fileId = typeof raw.file_id === 'string' ? raw.file_id : artifactId;
    const id = typeof raw.id === 'string' ? raw.id : artifactId;
    const fileName = typeof raw.file_name === 'string' ? raw.file_name : '';
    if (!id || !fileId || !fileName) return [];
    return [{ id, fileId, fileName, contentType: typeof raw.content_type === 'string' ? raw.content_type : undefined, sizeBytes: typeof raw.size_bytes === 'number' ? raw.size_bytes : undefined }];
  });
}

function toRagSources(value: unknown): ChatRagSource[] {
  return Array.isArray(value) ? value.filter((item): item is ChatRagSource => !!item && typeof item === 'object') : [];
}

function toMessageMeta(value: unknown): ChatMessageMeta | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const raw = value as Record<string, unknown>;
  const meta: ChatMessageMeta = {
    attachments: toAttachments(raw.attachments),
    ragSources: toRagSources(raw.rag_sources),
    runtimeRunId: typeof raw.runtime_run_id === 'string' ? raw.runtime_run_id : undefined,
  };
  return meta.attachments?.length || meta.ragSources?.length || meta.runtimeRunId ? meta : undefined;
}

function toRenderableMessage(message: ChatMessage): Message | null {
  if (message.role !== 'user' && message.role !== 'assistant') {
    return null;
  }
  return {
    id: message.id,
    role: message.role,
    content: typeof message.content === 'string' ? message.content : String(message.content ?? ''),
    createdAt: message.created_at ?? new Date().toISOString(),
    meta: toMessageMeta(message.meta),
  };
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messagesByChat, setMessagesByChat] = useState<Record<string, { items: Message[]; loading: boolean; loaded?: boolean }>>({});
  const [activeRun, setActiveRun] = useState<ActiveChatRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [pendingConfirmations, setPendingConfirmations] = useState<PendingConfirmation[]>([]);
  const [pendingConfirmationTokens, setPendingConfirmationTokens] = useState<string[]>([]);
  const [pendingInput, setPendingInput] = useState<PendingInput | null>(null);
  const [stopReason, setStopReason] = useState<string | null>(null);
  const [pausedRunId, setPausedRunId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const { data: chats } = useChats();
  const queryClient = useQueryClient();
  const chatItems = chats?.items ?? [];
  const chatsOrder = chatItems.map((chat) => chat.id);
  const chatsById = chatItems.reduce<Record<string, Chat>>((acc, chat) => {
    acc[chat.id] = chat;
    return acc;
  }, {});

  const loadMessages = useCallback(async (chatId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const chatsApi = await import('@shared/api/chats');
      const resp = await chatsApi.listMessages(chatId, 100);
      const items = Array.isArray(resp?.items)
        ? resp.items
            .map((item) => toRenderableMessage(item))
            .filter((item): item is Message => item !== null)
        : [];
      setMessagesByChat(prev => ({
        ...prev,
        [chatId]: { items, loading: false, loaded: true }
      }));
    } catch (err: unknown) {
      setMessagesByChat(prev => ({
        ...prev,
        [chatId]: { items: [], loading: false, loaded: true }
      }));
      setError(err instanceof Error ? err.message : 'Ошибка загрузки сообщений');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const setCurrentChat = useCallback((_chatId: string) => {}, []);

  const clearPendingState = useCallback(() => {
    setPendingConfirmations([]);
    setPendingConfirmationTokens([]);
    setPendingInput(null);
    setStopReason(null);
    setPausedRunId(null);
    setActiveRun(null);
  }, []);

  const abortStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  const applyPausedState = useCallback((resumeState: ResumePausedState) => {
    const reason = (resumeState.reason || '').trim() || 'paused';
    const question = (resumeState.question || '').trim();
    const message = (resumeState.message || '').trim();
    const runId = (resumeState.runId || '').trim();
    const action = resumeState.action || {};

    setStopReason(reason);
    setPausedRunId(runId || null);

    if (reason === 'waiting_confirmation') {
      setPendingConfirmations([{
        operationFingerprint: String(action.operation_fingerprint || ''),
        toolSlug: String(action.tool_slug || ''),
        operation: String(action.operation || ''),
        riskLevel: String(action.risk_level || 'write'),
        argsPreview: String(action.args_preview || ''),
        summary: message || question || 'Требуется подтверждение',
        runId: runId || null,
      }]);
      setPendingInput(null);
      setActiveRun((current) => current ? { ...current, runId: runId || current.runId, status: 'waiting_confirmation' } : current);
      return;
    }

    setPendingConfirmations([]);
    setPendingInput({
      question: question || message || undefined,
      reason,
    });
    setActiveRun((current) => current ? { ...current, runId: runId || current.runId, status: 'waiting_input' } : current);
  }, []);

  const sendMessageStream = useCallback(async (
    chatId: string,
    message: string,
    useRag: boolean,
    onChunk: (chunk: string) => void,
    onError: (error: string) => void,
    agentSlug?: string,
    attachmentIds?: string[],
    attachmentMeta?: unknown[],
    confirmationTokens?: string[]
  ) => {
    try {
      setError(null);
      setPendingConfirmations([]);
      setPendingInput(null);
      setStopReason(null);
      setPausedRunId(null);
      setActiveRun(null);
      if (confirmationTokens?.length) {
        setPendingConfirmationTokens((prev) => {
          const merged = [...prev, ...confirmationTokens];
          return Array.from(new Set(merged.filter(Boolean)));
        });
      }

      // 1. Optimistically add user message to local state
      const tempUserId = `temp-user-${Date.now()}`;
      const userMessage: Message = {
        id: tempUserId,
        role: 'user',
        content: message,
        createdAt: new Date().toISOString(),
        isOptimistic: true,
        meta: attachmentMeta?.length ? { attachments: toAttachments(attachmentMeta) } : undefined,
      };

      setMessagesByChat(prev => {
        const current = prev[chatId] || { items: [], loading: false, loaded: true };
        return {
          ...prev,
          [chatId]: {
            ...current,
            items: [...current.items, userMessage]
          }
        };
      });

      // 2. Create empty assistant message placeholder
      const tempAssistantId = `temp-assistant-${Date.now()}`;
      const assistantMessage: Message = {
        id: tempAssistantId,
        role: 'assistant',
        content: '',
        createdAt: new Date().toISOString(),
        isOptimistic: true
      };

      setMessagesByChat(prev => {
        const current = prev[chatId] || { items: [], loading: false, loaded: true };
        return {
          ...prev,
          [chatId]: {
            ...current,
            items: [...current.items, assistantMessage]
          }
        };
      });

      setActiveRun({
        userMessageId: tempUserId,
        assistantMessageId: tempAssistantId,
        progress: [],
        status: 'running',
      });

      const controller = new AbortController();
      abortControllerRef.current = controller;
      setIsStreaming(true);

      const { fetchStreamWithAuth } = await import('@shared/api/streamAuth');
      const response = await fetchStreamWithAuth(`/chats/${chatId}/messages`, {
        signal: controller.signal,
        body: {
          content: message,
          use_rag: useRag,
          agent_slug: agentSlug,
          execution_mode: 'normal',
          attachment_ids: attachmentIds ?? [],
          confirmation_tokens: confirmationTokens ?? [],
        },
      });

      if (!response.ok || !response.body) {
        // Try to extract backend error details
        let reason = 'Ошибка отправки сообщения';
        try {
          const text = await response.text();
          try {
            const j = JSON.parse(text);
            reason = (j && (j.detail || j.error)) || reason;
          } catch {
            reason = text || reason;
          }
        } catch {}
        throw new Error(reason);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = '';
      let assistantContent = '';
      let pendingRenderedContent = '';
      let flushTimer: ReturnType<typeof setTimeout> | null = null;
      let realUserId: string | null = null;
      let realAssistantId: string | null = null;

      const flushAssistantContent = () => {
        setMessagesByChat(prev => {
          const current = prev[chatId];
          if (!current) return prev;
          return {
            ...prev,
            [chatId]: {
              ...current,
              items: current.items.map(m =>
                m.id === tempAssistantId ? { ...m, content: pendingRenderedContent } : m
              )
            }
          };
        });
      };

      const scheduleFlush = () => {
        if (flushTimer) return;
        flushTimer = setTimeout(() => {
          flushTimer = null;
          flushAssistantContent();
        }, 40);
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        let sepIdx;
        while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
          const rawEvent = buffer.slice(0, sepIdx);
          buffer = buffer.slice(sepIdx + 2);

          const lines = rawEvent.split('\n');
          const eventLine = lines.find(l => l.startsWith('event:')) || '';
          const dataLines = lines.filter(l => l.startsWith('data:'));

          const eventType = eventLine.replace('event:', '').trim();
          // Join multiple data: lines with a newline per SSE spec, preserving whitespace
          const data = dataLines
            .map(dl => {
              let val = dl.slice(5);
              if (val.startsWith(' ')) val = val.slice(1);
              return val;
            })
            .join('\n');

          if (data === '[DONE]') {
            buffer = '';
            break;
          }

          if (eventType === 'user_message') {
            try {
              const parsed = JSON.parse(data);
              realUserId = parsed.message_id;
              const userCreatedAt = parsed.created_at;
              setActiveRun((current) => current?.userMessageId === tempUserId ? { ...current, userMessageId: realUserId! } : current);
              // Update temp user message with real ID and created_at from backend
              setMessagesByChat(prev => {
                const current = prev[chatId];
                if (!current) return prev;
                return {
                  ...prev,
                  [chatId]: {
                    ...current,
                    items: current.items.map(m =>
                      m.id === tempUserId ? { 
                        ...m, 
                        id: realUserId!, 
                        createdAt: userCreatedAt || m.createdAt,
                        isOptimistic: false 
                      } : m
                    )
                  }
                };
              });
            } catch (e) {
              console.error('Failed to parse user_message event', e);
            }
          }
          // Handle chat_title event (auto-generated title)
          else if (eventType === 'chat_title') {
            try {
              const parsed = JSON.parse(data);
              const newTitle = parsed.title;
              if (newTitle && chatId) {
                // Update chat title in cache immediately
                queryClient.setQueriesData(
                  { queryKey: qk.chats.all() },
                  (oldData: unknown) => {
                    if (!oldData || typeof oldData !== 'object') return oldData;
                    const typed = oldData as { items?: Array<Record<string, unknown>> };
                    if (!Array.isArray(typed.items)) return oldData;
                    return {
                      ...typed,
                      items: typed.items.map((chat) =>
                        chat.id === chatId ? { ...chat, name: newTitle } : chat
                      ),
                    };
                  }
                );
                // Also invalidate to ensure consistency
                queryClient.invalidateQueries({ queryKey: qk.chats.all() });
              }
            } catch (e) {
              console.error('Failed to parse chat_title event', e);
            }
          }
          // Runtime progress is the only safe execution detail exposed to chat.
          else if (eventType === 'status') {
            try {
              const parsed = JSON.parse(data) as { stage?: unknown; progress?: Record<string, unknown> };
              if (parsed.stage !== 'runtime_progress' || !parsed.progress) continue;
              const description = typeof parsed.progress.description === 'string' ? parsed.progress.description.trim() : '';
              if (description) {
                const progress: ChatRuntimeProgress = {
                  id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                  runId: typeof parsed.progress.run_id === 'string' ? parsed.progress.run_id : '',
                  phase: typeof parsed.progress.phase === 'string' ? parsed.progress.phase : '',
                  kind: typeof parsed.progress.kind === 'string' ? parsed.progress.kind : '',
                  description,
                  status: typeof parsed.progress.status === 'string' ? parsed.progress.status : undefined,
                  createdAt: new Date().toISOString(),
                };
                setActiveRun((current) => current ? {
                  ...current,
                  runId: progress.runId || current.runId,
                  progress: current.progress.at(-1)?.description === progress.description ? current.progress : [...current.progress, progress].slice(-10),
                } : current);
              }
            } catch {
              // Ignore malformed status frames.
            }
          }
          // Handle delta events
          else if (eventType === 'delta') {
            assistantContent += data;
            pendingRenderedContent = assistantContent;
            scheduleFlush();
            onChunk(assistantContent);
          }
          // Handle final event
          else if (eventType === 'final') {
            try {
              const parsed = JSON.parse(data);
              realAssistantId = parsed.message_id;
              const assistantCreatedAt = parsed.created_at;
              // Update sources if present in final event
              const finalSources = parsed.sources;
              const finalAttachments = Array.isArray(parsed.attachments) ? parsed.attachments : undefined;
              // Update temp assistant message with real ID, created_at and sources
              if (flushTimer) {
                clearTimeout(flushTimer);
                flushTimer = null;
              }
              pendingRenderedContent = assistantContent;
              flushAssistantContent();
              setMessagesByChat(prev => {
                const current = prev[chatId];
                if (!current) return prev;
                return {
                  ...prev,
                  [chatId]: {
                    ...current,
                    items: current.items.map(m =>
                      m.id === tempAssistantId ? { 
                        ...m, 
                        id: realAssistantId!, 
                        createdAt: assistantCreatedAt || m.createdAt,
                        isOptimistic: false,
                        meta: {
                          ragSources: toRagSources(finalSources),
                          attachments: toAttachments(finalAttachments),
                        }
                      } : m
                    )
                  }
                };
              });
            } catch (e) {
              console.error('Failed to parse final event', e);
            }
          }
          // `pause` is the only public pause event in the current contract.
          else if (eventType === 'pause') {
            try {
              const parsed = JSON.parse(data) as Record<string, unknown>;
              const context = parsed.context && typeof parsed.context === 'object'
                ? parsed.context as Record<string, unknown>
                : {};
              applyPausedState({
                runId: typeof parsed.run_id === 'string' ? parsed.run_id : null,
                reason: typeof parsed.reason === 'string' ? parsed.reason : 'paused',
                question: typeof context.question === 'string' ? context.question : undefined,
                message: typeof context.message === 'string' ? context.message : undefined,
                action: parsed.action && typeof parsed.action === 'object' ? parsed.action as Record<string, unknown> : {},
              });
            } catch {
              onError('Некорректное событие паузы');
            }
          }
          // Handle error events
          else if (eventType === 'error') {
            try {
              const parsed = JSON.parse(data);
              const errorMessage = String(parsed?.error || data || 'Ошибка');
              const errorCode = String(parsed?.code || '').trim();
              // Error must unblock the chat input.
              setPendingConfirmations([]);
              setPendingInput(null);
              setStopReason(null);
              setPausedRunId(null);
              if (errorCode) {
                onError(`${errorCode}: ${errorMessage}`);
              } else {
                onError(errorMessage);
              }
            } catch {
              setPendingConfirmations([]);
              setPendingInput(null);
              setStopReason(null);
              setPausedRunId(null);
              onError(data);
            }
          }
        }
      }

      // Progress is live-only and never becomes part of persisted history.
      setActiveRun(null);
      setPendingConfirmationTokens([]);
      if (flushTimer) {
        clearTimeout(flushTimer);
      }
      
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // User stopped generation — not an error
        setActiveRun(null);
        setPendingConfirmations([]);
        setPendingInput(null);
      } else {
        const errorMsg = err instanceof Error ? err.message : 'Ошибка отправки сообщения';
        setError(errorMsg);
        onError(errorMsg);
        setPendingConfirmations([]);
        setPendingInput(null);
        setStopReason(null);
        setPausedRunId(null);
        setActiveRun(null);
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [applyPausedState, queryClient]);

  const resumeStream = useCallback(async (
    runId: string,
    action: 'confirm' | 'cancel' | 'input',
    input: string,
    onChunk: (chunk: string) => void,
    onError: (error: string) => void,
  ) => {
    if (!runId) {
      onError('Run ID is required');
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setError(null);
    setIsStreaming(true);

    try {
      const { resumeRunStream } = await import('@shared/api/chats');
      const response = await resumeRunStream(runId, action, input || '', controller.signal);

      if (!response.ok || !response.body) {
        let reason = 'Ошибка возобновления';
        try {
          const text = await response.text();
          try {
            const j = JSON.parse(text);
            reason = (j && (j.detail || j.error)) || reason;
          } catch {
            reason = text || reason;
          }
        } catch {}
        throw new Error(reason);
      }

      await consumeSse(response, ({ event, data }) => {
        if (data === '[DONE]' || event === 'done') {
          clearPendingState();
          return;
        }
        if (event === 'delta') {
          onChunk(data);
          return;
        }
        if (event === 'final') {
          clearPendingState();
          return;
        }
        if (event === 'error') {
          const payload = JSON.parse(data) as { error?: unknown };
          throw new Error(typeof payload.error === 'string' ? payload.error : 'Ошибка возобновления');
        }
        if (event !== 'pause') return;
        const payload = JSON.parse(data) as Record<string, unknown>;
        const context = payload.context && typeof payload.context === 'object' ? payload.context as Record<string, unknown> : {};
        applyPausedState({
          runId: typeof payload.run_id === 'string' ? payload.run_id : null,
          reason: typeof payload.reason === 'string' ? payload.reason : 'paused',
          question: typeof context.question === 'string' ? context.question : undefined,
          message: typeof context.message === 'string' ? context.message : undefined,
          action: payload.action && typeof payload.action === 'object' ? payload.action as Record<string, unknown> : {},
        });
      });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setActiveRun(null);
      } else {
        const errorMsg = err instanceof Error ? err.message : 'Ошибка возобновления';
        setError(errorMsg);
        onError(errorMsg);
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [applyPausedState, clearPendingState]);

  const actionsValue = useMemo<ChatActions>(
    () => ({
      loadMessages,
      setCurrentChat,
      clearPendingState,
      applyPausedState,
      abortStream,
      sendMessageStream,
      resumeStream,
    }),
    [loadMessages, setCurrentChat, clearPendingState, applyPausedState, abortStream, sendMessageStream, resumeStream]
  );
  const messagesStateValue = useMemo(
    () => ({
      messagesByChat,
      activeRun,
      pendingConfirmations,
      pendingInput,
      pausedRunId,
      isStreaming,
      isLoading,
    }),
    [
      messagesByChat,
      activeRun,
      pendingConfirmations,
      pendingInput,
      pausedRunId,
      isStreaming,
      isLoading,
    ]
  );
  const catalogStateValue = useMemo(
    () => ({
      chatsOrder,
      chatsById,
      messagesByChat,
    }),
    [chatsOrder, chatsById, messagesByChat]
  );

  return (
    <ChatActionsContext.Provider value={actionsValue}>
      <ChatMessagesStateContext.Provider value={messagesStateValue}>
        <ChatCatalogStateContext.Provider value={catalogStateValue}>
          {children}
        </ChatCatalogStateContext.Provider>
      </ChatMessagesStateContext.Provider>
    </ChatActionsContext.Provider>
  );
}

export function useChatActions() {
  const context = useContext(ChatActionsContext);
  if (!context) {
    throw new Error('useChatActions must be used within ChatProvider');
  }
  return context;
}

export function useChatMessagesState() {
  const context = useContext(ChatMessagesStateContext);
  if (!context) {
    throw new Error('useChatMessagesState must be used within ChatProvider');
  }
  return context;
}

export function useChatCatalogState() {
  const context = useContext(ChatCatalogStateContext);
  if (!context) {
    throw new Error('useChatCatalogState must be used within ChatProvider');
  }
  return context;
}
