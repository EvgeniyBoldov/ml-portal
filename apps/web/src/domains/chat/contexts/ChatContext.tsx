import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { useChats } from '@shared/api/hooks/useChats';
import { useQueryClient } from '@tanstack/react-query';
import type { Chat, ChatMessage } from '@shared/api/types';

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
}

interface ChatContextValue {
  state: ChatState;
  loadMessages: (chatId: string) => Promise<void>;
  setCurrentChat: (chatId: string) => void;
  clearPendingState: () => void;
  applyPausedState: (state: ResumePausedState) => void;
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
}

const ChatContext = createContext<ChatContextValue | null>(null);

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

  const clearPendingState = useCallback(() => {
    setPendingConfirmations([]);
    setPendingConfirmationTokens([]);
    setPendingInput(null);
    setStopReason(null);
    setPausedRunId(null);
    setOrchestrationEnvelope(null);
    setOrchestrationState(null);
    setStreamStatus(null);
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
      setStreamStatus('Ожидание подтверждения...');
      return;
    }

    setPendingConfirmations([]);
    setPendingInput({
      question: question || message || undefined,
      reason,
    });
    setStreamStatus('Ожидание ввода...');
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
      setStreamStatus(null);
      setPendingConfirmations([]);
      setPendingInput(null);
      setStopReason(null);
      setPausedRunId(null);
      setOrchestrationEnvelope(null);
      setOrchestrationState(null);
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

      const { API_BASE } = await import('@shared/config');
      const { getAccessToken } = await import('@shared/api/http');
      const url = `${API_BASE}/chats/${chatId}/messages`;
      
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      };
      
      // Add auth token if available
      const token = getAccessToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      
      const response = await fetch(url, {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify({
          content: message,
          use_rag: useRag,
          agent_slug: agentSlug,
          attachment_ids: attachmentIds ?? [],
          confirmation_tokens: confirmationTokens ?? [],
        }),
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
                queryClient.setQueryData(['chats', 'list'], (oldData: any) => {
                  if (!oldData?.items) return oldData;
                  return {
                    ...oldData,
                    items: oldData.items.map((chat: any) =>
                      chat.id === chatId ? { ...chat, name: newTitle } : chat
                    ),
                  };
                });
                // Also invalidate to ensure consistency
                queryClient.invalidateQueries({ queryKey: ['chats'] });
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
                  setStreamStatus(null);
                } else {
                  setStreamStatus(statusText);
                }
              } else if (stage.startsWith('thinking_step_')) {
                // Handle dynamic thinking steps
                setStreamStatus('Думаю...');
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
              setStreamStatus(`${displayName}...`);
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
              setStreamStatus('Генерирую ответ...');
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
                  setStreamStatus(`Шаг ${iteration}: ${agentSlug} (${phaseTitle})...`);
                } else {
                  setStreamStatus(`Шаг ${iteration}: ${agentSlug}...`);
                }
              } else if (actionType === 'final' || stepType === 'finalize') {
                setStreamStatus('Формирую ответ...');
              } else if (actionType === 'ask_user' || stepType === 'ask_user') {
                setStreamStatus('Нужно уточнение...');
              } else {
                setStreamStatus(`Планирую шаг ${iteration}...`);
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
              setStreamStatus('Ожидание подтверждения...');
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
              setPendingInput({
                question: parsed.question,
                reason: parsed.reason,
              });
              setStreamStatus('Ожидание ввода...');
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
              setStopReason(parsed.reason || 'stopped');
              if (parsed.run_id) {
                setPausedRunId(parsed.run_id);
              }
            } catch (e) {
              console.error('Failed to parse stop event', e);
            }
          }
          // Handle agent_selected events
          else if (eventType === 'agent_selected') {
            try {
              const parsed = JSON.parse(data);
              if (parsed.auto) {
                setStreamStatus(`Выбран агент: ${parsed.agent}`);
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
              setStreamStatus(null);
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
              setStreamStatus(null);
              onError(data);
            }
          }
        }
      }

      // Clear stream status after completion
      setStreamStatus(null);
      setPendingConfirmationTokens([]);
      setOrchestrationEnvelope(null);
      setOrchestrationState(null);
      if (flushTimer) {
        clearTimeout(flushTimer);
      }
      
    } catch (err: any) {
      const errorMsg = err?.message || 'Ошибка отправки сообщения';
      setError(errorMsg);
      onError(errorMsg);
      setPendingConfirmations([]);
      setPendingInput(null);
      setStopReason(null);
      setPausedRunId(null);
      setStreamStatus(null);
      setOrchestrationEnvelope(null);
      setOrchestrationState(null);
    } finally {
    }
  }, []);

  const value: ChatContextValue = {
    state: {
      chatsOrder,
      chatsById,
      messagesByChat,
      error,
      isLoading,
      currentChatId,
      streamStatus,
      pendingConfirmations,
      pendingConfirmationTokens,
      pendingInput,
      stopReason,
      pausedRunId,
      orchestrationEnvelope,
      orchestrationState,
    },
    loadMessages,
    setCurrentChat,
    clearPendingState,
    applyPausedState,
    sendMessageStream,
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within ChatProvider');
  }
  return context;
}
