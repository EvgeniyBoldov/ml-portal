import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { useChats, useChatMessages, useSendMessage } from '@shared/api/hooks/useChats';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

interface ChatState {
  messagesByChat: Record<string, { items: Message[]; loading: boolean }>;
  error: string | null;
  isLoading: boolean;
  currentChatId: string | null;
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
  const [messagesByChat, setMessagesByChat] = useState<Record<string, { items: Message[]; loading: boolean }>>({});
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
        [chatId]: { items, loading: false }
      }));
    } catch (err: any) {
      setMessagesByChat(prev => ({
        ...prev,
        [chatId]: { items: [], loading: false }
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
      setIsLoading(true);
      setError(null);

      const { API_BASE } = await import('@shared/config');
      const url = `${API_BASE}/chats/${chatId}/messages`;
      
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ content: message, use_rag: useRag }),
      });

      if (!response.ok || !response.body) {
        throw new Error('Ошибка отправки сообщения');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = '';
      let rendered = '';

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
          const dataLine = lines.find(l => l.startsWith('data:')) || '';

          const eventType = eventLine.replace('event:', '').trim();
          const data = dataLine.replace('data:', '').trim();

          if (data === '[DONE]') {
            buffer = '';
            break;
          }

          if (eventType === 'delta') {
            rendered += data;
            onChunk(rendered);
          } else if (eventType === 'error') {
            onError(data);
          }
        }
      }

      await loadMessages(chatId);
      
    } catch (err: any) {
      const errorMsg = err?.message || 'Ошибка отправки сообщения';
      setError(errorMsg);
      onError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  }, [loadMessages]);

  const value: ChatContextValue = {
    state: {
      messagesByChat,
      error,
      isLoading,
      currentChatId,
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
