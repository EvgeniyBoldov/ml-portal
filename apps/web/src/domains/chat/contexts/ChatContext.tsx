import React, { createContext, useContext, useState, useCallback, useRef, ReactNode, useMemo } from 'react';
import { useChats } from '@shared/api/hooks/useChats';
import { useQueryClient } from '@tanstack/react-query';
import type { Chat, ChatMessage } from '@shared/api/types';
import { qk } from '@/shared/api/keys';

type MessageMeta = Record<string, unknown> & {
  rag_sources?: unknown[];
  attachments?: unknown[];
};

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  isOptimistic?: boolean;
  meta?: MessageMeta;
}

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

interface ChatProgressEvent {
  id: string;
  level: 'info' | 'warn' | 'error';
  text: string;
  source: string;
  created_at: string;
  details_code?: string;
}

interface OrchestrationEnvelope {
  phase?: string;
  event_type?: string;
  stage?: string;
  run_id?: string | null;
  chat_id?: string | null;
  sequence?: number;
  ts?: string;
}

interface OrchestrationState {
  run_status?: string;
  intent_type?: string;
  current_phase_id?: string;
  current_agent_slug?: string;
  open_questions?: string[];
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
  currentChatId: string | null;
  streamStatus: string | null;
  pendingConfirmations: PendingConfirmation[];
  pendingConfirmationTokens: string[];
  pendingInput: PendingInput | null;
  stopReason: string | null;
  pausedRunId: string | null;
  orchestrationEnvelope: OrchestrationEnvelope | null;
  orchestrationState: OrchestrationState | null;
  isStreaming: boolean;
  progressEvents: ChatProgressEvent[];
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

const ChatStatusContext = createContext<Pick<ChatState, "error" | "isLoading"> | null>(null);
const ChatActionsContext = createContext<ChatActions | null>(null);
const ChatMessagesStateContext = createContext<
  Pick<
    ChatState,
    | "messagesByChat"
    | "streamStatus"
    | "pendingConfirmations"
    | "pendingInput"
    | "pausedRunId"
    | "orchestrationEnvelope"
    | "orchestrationState"
    | "isStreaming"
    | "isLoading"
    | "progressEvents"
  > | null
>(null);
const ChatCatalogStateContext = createContext<
  Pick<ChatState, "chatsOrder" | "chatsById" | "messagesByChat"> | null
>(null);

function toRenderableMessage(message: ChatMessage): Message | null {
  if (message.role !== 'user' && message.role !== 'assistant') {
    return null;
  }
  return {
    id: message.id,
    role: message.role,
    content: typeof message.content === 'string' ? message.content : String(message.content ?? ''),
    created_at: message.created_at ?? new Date().toISOString(),
    meta: (message.meta as MessageMeta | undefined) ?? undefined,
  };
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messagesByChat, setMessagesByChat] = useState<Record<string, { items: Message[]; loading: boolean; loaded?: boolean }>>({});
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [pendingConfirmations, setPendingConfirmations] = useState<PendingConfirmation[]>([]);
  const [pendingConfirmationTokens, setPendingConfirmationTokens] = useState<string[]>([]);
  const [pendingInput, setPendingInput] = useState<PendingInput | null>(null);
  const [stopReason, setStopReason] = useState<string | null>(null);
  const [pausedRunId, setPausedRunId] = useState<string | null>(null);
  const [orchestrationEnvelope, setOrchestrationEnvelope] = useState<OrchestrationEnvelope | null>(null);
  const [orchestrationState, setOrchestrationState] = useState<OrchestrationState | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [progressEvents, setProgressEvents] = useState<ChatProgressEvent[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamStatusRef = useRef<string | null>(null);

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

  const setCurrentChat = useCallback((chatId: string) => {
    setCurrentChatId(chatId);
  }, []);

  const updateStreamStatus = useCallback((next: string | null) => {
    if (streamStatusRef.current === next) {
      return;
    }
    streamStatusRef.current = next;
    setStreamStatus(next);
  }, []);

  const clearPendingState = useCallback(() => {
    setPendingConfirmations([]);
    setPendingConfirmationTokens([]);
    setPendingInput(null);
    setStopReason(null);
    setPausedRunId(null);
    setOrchestrationEnvelope(null);
    setOrchestrationState(null);
    setProgressEvents([]);
    updateStreamStatus(null);
  }, [updateStreamStatus]);

  const appendProgressEvent = useCallback((text: string, opts?: { level?: 'info' | 'warn' | 'error'; source?: string; details_code?: string }) => {
    const normalized = text.trim();
    if (!normalized) return;
    setProgressEvents((prev) => {
      const next = [...prev, {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        level: opts?.level || 'info',
        text: normalized,
        source: opts?.source || 'runtime',
        created_at: new Date().toISOString(),
        details_code: opts?.details_code,
      }];
      return next.slice(-10);
    });
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
      updateStreamStatus('Ожидание подтверждения...');
      return;
    }

    setPendingConfirmations([]);
    setPendingInput({
      question: question || message || undefined,
      reason,
    });
    updateStreamStatus('Ожидание ввода...');
  }, [updateStreamStatus]);

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
      updateStreamStatus(null);
      setPendingConfirmations([]);
      setPendingInput(null);
      setStopReason(null);
      setPausedRunId(null);
      setOrchestrationEnvelope(null);
      setOrchestrationState(null);
      setProgressEvents([]);
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
        created_at: new Date().toISOString(),
        isOptimistic: true,
        meta: attachmentMeta?.length ? { attachments: attachmentMeta } : undefined,
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
        created_at: new Date().toISOString(),
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

          // Handle user_message event
          const applyEnvelope = (parsed: Record<string, unknown>) => {
            const raw = parsed.orchestration_envelope;
            if (!raw || typeof raw !== 'object') return;
            setOrchestrationEnvelope(raw as OrchestrationEnvelope);
          };
          const applyOrchestrationState = (parsed: Record<string, unknown>) => {
            const raw = parsed.orchestration_state;
            if (!raw || typeof raw !== 'object') return;
            setOrchestrationState(raw as OrchestrationState);
          };

          if (eventType === 'user_message') {
            try {
              const parsed = JSON.parse(data);
              realUserId = parsed.message_id;
              const userCreatedAt = parsed.created_at;
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
                        created_at: userCreatedAt || m.created_at,
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
          // Handle status events
          else if (eventType === 'status') {
            try {
              const parsed = JSON.parse(data);
              applyEnvelope(parsed as Record<string, unknown>);
              applyOrchestrationState(parsed as Record<string, unknown>);
              const stage = parsed.stage || '';
              
              // Handle RAG sources if present
              if (parsed.sources && Array.isArray(parsed.sources)) {
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
                            meta: { ...m.meta, rag_sources: parsed.sources } 
                        } : m
                      )
                    }
                  };
                });
              }

              // Map stage to user-friendly status
              const statusMap: Record<string, string> = {
                'saving_user_message': 'Сохраняю сообщение...',
                'loading_agent': 'Загружаю агента...',
                'loading_context': 'Загружаю контекст...',
                'agent_running': 'Агент работает...',
                'thinking_step_1': 'Анализирую запрос...',
                'thinking_step_2': 'Обрабатываю результаты...',
                'thinking_step_3': 'Формирую ответ...',
                'streaming': 'Генерирую ответ...',
                'rbac_agent_invoke_denied': 'Нет прав на запуск агента...',
                'completed': '',
                // Legacy stages (for backward compatibility)
                'rag_search_started': 'Ищу в базе знаний...',
                'rag_search_done': 'Нашёл документы...',
                'rag_no_results': 'Документы не найдены',
                'generating_answer_started': 'Генерирую ответ...',
                'generating_answer_finished': ''
              };
              const statusText = statusMap[stage];
              if (statusText !== undefined) {
                if (statusText === '') {
                  updateStreamStatus(null);
                } else {
                  updateStreamStatus(statusText);
                  appendProgressEvent(statusText.replace(/\.\.\.$/, ''), { source: 'status' });
                }
              } else if (stage.startsWith('thinking_step_')) {
                // Handle dynamic thinking steps
                updateStreamStatus('Думаю...');
                appendProgressEvent('Думаю', { source: 'thinking' });
              }
            } catch (e) {
              console.error('Failed to parse status event', e);
            }
          }
          // Handle tool_call events (show status that tool is being called)
          else if (eventType === 'tool_call') {
            try {
              const parsed = JSON.parse(data);
              const toolName = parsed.tool || 'инструмент';
              // Map tool slugs to user-friendly names
              const toolNames: Record<string, string> = {
                'rag.search': 'Поиск в базе знаний'
              };
              const displayName = toolNames[toolName] || toolName;
              updateStreamStatus(`${displayName}...`);
              appendProgressEvent(`Инструмент: ${displayName}`, { source: 'tool_call' });
            } catch (e) {
              console.error('Failed to parse tool_call event', e);
            }
          }
          // Handle tool_result events (update sources from RAG tool)
          else if (eventType === 'tool_result') {
            try {
              const parsed = JSON.parse(data);
              // If this is rag.search result, extract sources
              if (parsed.tool === 'rag.search' && parsed.success && parsed.data?.hits) {
                const sources = parsed.data.hits.map((hit: any) => ({
                  source_id: hit.source_id || '',
                  source_name: hit.source_name || '',
                  text: hit.text?.slice(0, 200) || '',
                  page: hit.page,
                  score: hit.score
                }));
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
                          meta: { ...m.meta, rag_sources: sources } 
                        } : m
                      )
                    }
                  };
                });
              }
              updateStreamStatus('Генерирую ответ...');
              appendProgressEvent('Генерирую ответ', { source: 'tool_result' });
            } catch (e) {
              console.error('Failed to parse tool_result event', e);
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
                        created_at: assistantCreatedAt || m.created_at,
                        isOptimistic: false,
                        meta: finalSources?.length ? { ...m.meta, rag_sources: finalSources } : m.meta
                      } : m
                    )
                  }
                };
              });
            } catch (e) {
              console.error('Failed to parse final event', e);
            }
          }
          // Handle planner_action events
          else if (eventType === 'planner_action') {
            try {
              const parsed = JSON.parse(data);
              applyEnvelope(parsed as Record<string, unknown>);
              applyOrchestrationState(parsed as Record<string, unknown>);
              const actionType = String(parsed.action_type || '').trim();
              const stepType = String(parsed.step_type || '').trim();
              const iteration = Number(parsed.iteration || 0);
              const agentSlug = String(parsed.agent_slug || parsed.tool_slug || '').trim();
              const phaseTitle = String(parsed.phase_title || '').trim();
              if ((actionType === 'agent_call' || stepType === 'call_agent') && agentSlug) {
                if (phaseTitle) {
                  updateStreamStatus(`Шаг ${iteration}: ${agentSlug} (${phaseTitle})...`);
                  appendProgressEvent(`Шаг ${iteration}: ${agentSlug} (${phaseTitle})`, { source: 'planner' });
                } else {
                  updateStreamStatus(`Шаг ${iteration}: ${agentSlug}...`);
                  appendProgressEvent(`Шаг ${iteration}: ${agentSlug}`, { source: 'planner' });
                }
              } else if (actionType === 'final' || stepType === 'finalize') {
                updateStreamStatus('Формирую ответ...');
                appendProgressEvent('Формирую ответ', { source: 'planner' });
              } else if (actionType === 'ask_user' || stepType === 'ask_user') {
                updateStreamStatus('Нужно уточнение...');
                appendProgressEvent('Нужно уточнение', { source: 'planner', level: 'warn' });
              } else {
                updateStreamStatus(`Планирую шаг ${iteration}...`);
                appendProgressEvent(`Планирую шаг ${iteration}`, { source: 'planner' });
              }
            } catch (e) {
              console.error('Failed to parse planner_action event', e);
            }
          }
          // Handle confirmation_required events
          else if (eventType === 'confirmation_required') {
            try {
              const parsed = JSON.parse(data);
              setPendingConfirmations((prev) => [
                ...prev,
                {
                  operationFingerprint: String(parsed.operation_fingerprint || ''),
                  toolSlug: String(parsed.tool_slug || ''),
                  operation: String(parsed.operation || ''),
                  riskLevel: String(parsed.risk_level || 'write'),
                  argsPreview: String(parsed.args_preview || ''),
                  summary: String(parsed.summary || parsed.message || 'Требуется подтверждение'),
                  runId: typeof parsed.run_id === 'string' ? parsed.run_id : null,
                },
              ]);
              updateStreamStatus('Ожидание подтверждения...');
              appendProgressEvent('Ожидание подтверждения', { source: 'confirmation', level: 'warn' });
            } catch (e) {
              console.error('Failed to parse confirmation_required event', e);
            }
          }
          // Handle waiting_input events
          else if (eventType === 'waiting_input') {
            try {
              const parsed = JSON.parse(data);
              applyEnvelope(parsed as Record<string, unknown>);
              applyOrchestrationState(parsed as Record<string, unknown>);
              applyPausedState({
                runId: typeof parsed.run_id === 'string' ? parsed.run_id : null,
                reason: typeof parsed.reason === 'string' ? parsed.reason : 'waiting_input',
                question: typeof parsed.question === 'string' ? parsed.question : undefined,
                message: typeof parsed.message === 'string' ? parsed.message : undefined,
                action: (parsed.action && typeof parsed.action === 'object' ? parsed.action : null) as Record<string, unknown> | null,
              });
              appendProgressEvent('Ожидание ввода', { source: 'waiting_input', level: 'warn' });
            } catch (e) {
              console.error('Failed to parse waiting_input event', e);
            }
          }
          // Handle stop events
          else if (eventType === 'stop') {
            try {
              const parsed = JSON.parse(data);
              applyEnvelope(parsed as Record<string, unknown>);
              applyOrchestrationState(parsed as Record<string, unknown>);
              applyPausedState({
                runId: typeof parsed.run_id === 'string' ? parsed.run_id : null,
                reason: typeof parsed.reason === 'string' ? parsed.reason : 'paused',
                question: typeof parsed.question === 'string' ? parsed.question : undefined,
                message: typeof parsed.message === 'string' ? parsed.message : undefined,
                action: (parsed.action && typeof parsed.action === 'object' ? parsed.action : null) as Record<string, unknown> | null,
              });
            } catch (e) {
              console.error('Failed to parse stop event', e);
            }
          }
          // Handle agent_selected events
          else if (eventType === 'agent_selected') {
            try {
              const parsed = JSON.parse(data);
              if (parsed.auto) {
                updateStreamStatus(`Выбран агент: ${parsed.agent}`);
                appendProgressEvent(`Выбран агент: ${parsed.agent}`, { source: 'agent_selected' });
              }
            } catch (e) {
              console.error('Failed to parse agent_selected event', e);
            }
          }
          // Handle error events
          else if (eventType === 'error') {
            try {
              const parsed = JSON.parse(data);
              applyEnvelope(parsed as Record<string, unknown>);
              applyOrchestrationState(parsed as Record<string, unknown>);
              const errorMessage = String(parsed?.error || data || 'Ошибка');
              const errorCode = String(parsed?.code || '').trim();
              // Error must unblock chat input. Waiting states are valid only on explicit
              // waiting_input / confirmation_required + stop events.
              setPendingConfirmations([]);
              setPendingInput(null);
              setStopReason(null);
              setPausedRunId(null);
              updateStreamStatus(null);
              if (errorCode) {
                onError(`${errorCode}: ${errorMessage}`);
              } else {
                onError(errorMessage);
              }
              appendProgressEvent(`Ошибка: ${errorCode || 'runtime'}`, { source: 'error', level: 'error', details_code: errorCode || undefined });
            } catch {
              setPendingConfirmations([]);
              setPendingInput(null);
              setStopReason(null);
              setPausedRunId(null);
              updateStreamStatus(null);
              onError(data);
            }
          }
        }
      }

      // Clear stream status after completion
      updateStreamStatus(null);
      setProgressEvents([]);
      setPendingConfirmationTokens([]);
      setOrchestrationEnvelope(null);
      setOrchestrationState(null);
      if (flushTimer) {
        clearTimeout(flushTimer);
      }
      
    } catch (err: any) {
      if (err?.name === 'AbortError') {
        // User stopped generation — not an error
        updateStreamStatus(null);
        setPendingConfirmations([]);
        setPendingInput(null);
      } else {
        const errorMsg = err?.message || 'Ошибка отправки сообщения';
        setError(errorMsg);
        onError(errorMsg);
        setPendingConfirmations([]);
        setPendingInput(null);
        setStopReason(null);
        setPausedRunId(null);
        updateStreamStatus(null);
        setOrchestrationEnvelope(null);
        setOrchestrationState(null);
        setProgressEvents([]);
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [appendProgressEvent, applyPausedState, updateStreamStatus]);

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

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

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

          const applyEnvelope = (parsed: Record<string, unknown>) => {
            const raw = parsed.orchestration_envelope;
            if (!raw || typeof raw !== 'object') return;
            setOrchestrationEnvelope(raw as OrchestrationEnvelope);
          };
          const applyOrchestrationState = (parsed: Record<string, unknown>) => {
            const raw = parsed.orchestration_state;
            if (!raw || typeof raw !== 'object') return;
            setOrchestrationState(raw as OrchestrationState);
          };

          try {
            const parsed = JSON.parse(data);
            const type = parsed.type || eventType;

            if (type === 'chunk' || type === 'delta') {
              const chunkText = typeof parsed.text === 'string' ? parsed.text : '';
              if (chunkText) onChunk(chunkText);
            } else if (type === 'run_paused' || type === 'stop') {
              applyEnvelope(parsed as Record<string, unknown>);
              applyOrchestrationState(parsed as Record<string, unknown>);
              applyPausedState({
                runId: typeof parsed.run_id === 'string' ? parsed.run_id : null,
                reason: typeof parsed.reason === 'string' ? parsed.reason : 'paused',
                question: typeof parsed.question === 'string' ? parsed.question : undefined,
                message: typeof parsed.message === 'string' ? parsed.message : undefined,
                action: parsed.action as Record<string, unknown> | undefined,
              });
            } else if (type === 'confirmation_required') {
              // Pause for confirmation
              // Remove last agent message if it matches the confirmation question (avoid duplication)
              const confirmationText = typeof parsed.summary === 'string' ? parsed.summary : '';
              setMessagesByChat((prev) => {
                if (!currentChatId) return prev;
                const current = prev[currentChatId];
                if (!current) return prev;
                const items = current.items;
                const lastMsg = items[items.length - 1];
                if (lastMsg && lastMsg.role === 'assistant' && lastMsg.content === confirmationText) {
                  return {
                    ...prev,
                    [currentChatId]: { ...current, items: items.slice(0, -1) }
                  };
                }
                return prev;
              });
              applyEnvelope(parsed as Record<string, unknown>);
              applyOrchestrationState(parsed as Record<string, unknown>);
              applyPausedState({
                runId: typeof parsed.run_id === 'string' ? parsed.run_id : null,
                reason: 'waiting_confirmation',
                question: typeof parsed.summary === 'string' ? parsed.summary : undefined,
                message: typeof parsed.message === 'string' ? parsed.message : undefined,
                action: {
                  operation_fingerprint: parsed.operation_fingerprint,
                  tool_slug: parsed.tool_slug,
                  operation: parsed.operation,
                  risk_level: parsed.risk_level,
                  args_preview: parsed.args_preview,
                } as Record<string, unknown>,
              });
            } else if (type === 'waiting_input') {
              // Pause for user input
              // Remove last agent message if it matches the input question (avoid duplication)
              const questionText = typeof parsed.question === 'string' ? parsed.question : '';
              setMessagesByChat((prev) => {
                if (!currentChatId) return prev;
                const current = prev[currentChatId];
                if (!current) return prev;
                const items = current.items;
                const lastMsg = items[items.length - 1];
                if (lastMsg && lastMsg.role === 'assistant' && lastMsg.content === questionText) {
                  return {
                    ...prev,
                    [currentChatId]: { ...current, items: items.slice(0, -1) }
                  };
                }
                return prev;
              });
              applyEnvelope(parsed as Record<string, unknown>);
              applyOrchestrationState(parsed as Record<string, unknown>);
              applyPausedState({
                runId: typeof parsed.run_id === 'string' ? parsed.run_id : null,
                reason: 'waiting_input',
                question: typeof parsed.question === 'string' ? parsed.question : undefined,
                message: typeof parsed.reason === 'string' ? parsed.reason : undefined,
              });
            } else if (type === 'error') {
              const errorMsg = typeof parsed.error === 'string' ? parsed.error : 'Unknown error';
              throw new Error(errorMsg);
            } else if (type === 'final' || type === 'done' || data === '[DONE]') {
              // Stream completed - close prompt window
              clearPendingState();
            }
          } catch (_e) {
            // Non-JSON lines are ignored
          }
        }
      }
    } catch (err: any) {
      if (err?.name === 'AbortError') {
        updateStreamStatus(null);
      } else {
        const errorMsg = err?.message || 'Ошибка возобновления';
        setError(errorMsg);
        onError(errorMsg);
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [applyPausedState, clearPendingState, updateStreamStatus, currentChatId]);

  const statusValue = useMemo(
    () => ({ error, isLoading }),
    [error, isLoading]
  );
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
      streamStatus,
      pendingConfirmations,
      pendingInput,
      pausedRunId,
      orchestrationEnvelope,
      orchestrationState,
      isStreaming,
      isLoading,
      progressEvents,
    }),
    [
      messagesByChat,
      streamStatus,
      pendingConfirmations,
      pendingInput,
      pausedRunId,
      orchestrationEnvelope,
      orchestrationState,
      isStreaming,
      isLoading,
      progressEvents,
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
    <ChatStatusContext.Provider value={statusValue}>
      <ChatActionsContext.Provider value={actionsValue}>
        <ChatMessagesStateContext.Provider value={messagesStateValue}>
          <ChatCatalogStateContext.Provider value={catalogStateValue}>
            {children}
          </ChatCatalogStateContext.Provider>
        </ChatMessagesStateContext.Provider>
      </ChatActionsContext.Provider>
    </ChatStatusContext.Provider>
  );
}

export function useChatStatusState() {
  const context = useContext(ChatStatusContext);
  if (!context) {
    throw new Error('useChatStatusState must be used within ChatProvider');
  }
  return context;
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
