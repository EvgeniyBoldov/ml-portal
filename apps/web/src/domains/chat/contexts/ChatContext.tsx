import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { useChats, useChatMessages, useSendMessage } from '@shared/api/hooks/useChats';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  isOptimistic?: boolean;
}

interface ChatState {
  messagesByChat: Record<string, { items: Message[]; loading: boolean; loaded?: boolean }>;
  error: string | null;
  isLoading: boolean;
  currentChatId: string | null;
  streamStatus: string | null;
}

interface ChatContextValue {
  state: ChatState;
  loadMessages: (chatId: string) => Promise<void>;
  setCurrentChat: (chatId: string) => void;
  sendMessageStream: (
    chatId: string,
    message: string,
    useRag: boolean,
    onChunk: (chunk: string) => void,
    onError: (error: string) => void
  ) => Promise<void>;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messagesByChat, setMessagesByChat] = useState<Record<string, { items: Message[]; loading: boolean; loaded?: boolean }>>({});
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);

  const { data: chats } = useChats();
  const sendMessageMutation = useSendMessage();

  const loadMessages = useCallback(async (chatId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const chatsApi = await import('@shared/api/chats');
      const resp = await chatsApi.listMessages(chatId, 100);
      const items = Array.isArray((resp as any)?.items) ? (resp as any).items : [];
      setMessagesByChat(prev => ({
        ...prev,
        [chatId]: { items, loading: false, loaded: true }
      }));
    } catch (err: any) {
      setMessagesByChat(prev => ({
        ...prev,
        [chatId]: { items: [], loading: false, loaded: true }
      }));
      setError(err?.message || 'Ошибка загрузки сообщений');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const setCurrentChat = useCallback((chatId: string) => {
    setCurrentChatId(chatId);
  }, []);

  const sendMessageStream = useCallback(async (
    chatId: string,
    message: string,
    useRag: boolean,
    onChunk: (chunk: string) => void,
    onError: (error: string) => void
  ) => {
    try {
      setError(null);
      setStreamStatus(null);

      // 1. Optimistically add user message to local state
      const tempUserId = `temp-user-${Date.now()}`;
      const userMessage: Message = {
        id: tempUserId,
        role: 'user',
        content: message,
        created_at: new Date().toISOString(),
        isOptimistic: true
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
        body: JSON.stringify({ content: message, use_rag: useRag }),
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
      let realUserId: string | null = null;
      let realAssistantId: string | null = null;

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
          if (eventType === 'user_message') {
            try {
              const parsed = JSON.parse(data);
              realUserId = parsed.message_id;
              // Update temp user message with real ID
              setMessagesByChat(prev => {
                const current = prev[chatId];
                if (!current) return prev;
                return {
                  ...prev,
                  [chatId]: {
                    ...current,
                    items: current.items.map(m =>
                      m.id === tempUserId ? { ...m, id: realUserId!, isOptimistic: false } : m
                    )
                  }
                };
              });
            } catch (e) {
              console.error('Failed to parse user_message event', e);
            }
          }
          // Handle status events
          else if (eventType === 'status') {
            try {
              const parsed = JSON.parse(data);
              const stage = parsed.stage || '';
              // Map stage to user-friendly status
              const statusMap: Record<string, string> = {
                'saving_user_message': 'Сохраняю сообщение...',
                'loading_context': 'Загружаю контекст...',
                'rag_search_started': 'Ищу в базе знаний...',
                'rag_search_done': 'Нашёл документы...',
                'rag_no_results': 'Документы не найдены',
                'generating_answer_started': 'Генерирую ответ...',
                'generating_answer_finished': ''
              };
              const statusText = statusMap[stage] || 'Загрузка...';
              if (statusText) {
                setStreamStatus(statusText);
              } else if (stage === 'generating_answer_finished') {
                // Clear status when generation is finished
                setStreamStatus(null);
              }
            } catch (e) {
              console.error('Failed to parse status event', e);
            }
          }
          // Handle delta events
          else if (eventType === 'delta') {
            assistantContent += data;
            // Update assistant message content in-place
            setMessagesByChat(prev => {
              const current = prev[chatId];
              if (!current) return prev;
              return {
                ...prev,
                [chatId]: {
                  ...current,
                  items: current.items.map(m =>
                    m.id === tempAssistantId ? { ...m, content: assistantContent } : m
                  )
                }
              };
            });
            onChunk(assistantContent);
          }
          // Handle final event
          else if (eventType === 'final') {
            try {
              const parsed = JSON.parse(data);
              realAssistantId = parsed.message_id;
              // Update temp assistant message with real ID
              setMessagesByChat(prev => {
                const current = prev[chatId];
                if (!current) return prev;
                return {
                  ...prev,
                  [chatId]: {
                    ...current,
                    items: current.items.map(m =>
                      m.id === tempAssistantId ? { ...m, id: realAssistantId!, isOptimistic: false } : m
                    )
                  }
                };
              });
            } catch (e) {
              console.error('Failed to parse final event', e);
            }
          }
          // Handle error events
          else if (eventType === 'error') {
            onError(data);
          }
        }
      }

      // Clear stream status after completion
      setStreamStatus(null);
      
    } catch (err: any) {
      const errorMsg = err?.message || 'Ошибка отправки сообщения';
      setError(errorMsg);
      onError(errorMsg);
      setStreamStatus(null);
    } finally {
    }
  }, []);

  const value: ChatContextValue = {
    state: {
      messagesByChat,
      error,
      isLoading,
      currentChatId,
      streamStatus,
    },
    loadMessages,
    setCurrentChat,
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
