import React, {
  createContext,
  useContext,
  useReducer,
  useEffect,
  useRef,
} from 'react';
import * as chatsApi from '@shared/api/chats';
import type { Chat, ChatMessage } from '@shared/api/types';

type MessagesState = {
  items: ChatMessage[];
  nextCursor: string | null;
  hasMore: boolean;
  loaded: boolean;
};

type ChatState = {
  isLoading: boolean;
  error: string | null;
  chatsOrder: string[];
  chatsById: Record<string, Chat>;
  messagesByChat: Record<string, MessagesState>;
  currentChatId: string | null;
};

type ChatAction =
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_CHATS'; payload: Chat[] }
  | { type: 'UPSERT_CHAT'; payload: Chat }
  | { type: 'DELETE_CHAT'; payload: string }
  | { type: 'SET_CURRENT_CHAT'; payload: string | null }
  | {
      type: 'SET_MESSAGES';
      payload: {
        chatId: string;
        items: ChatMessage[];
        nextCursor: string | null;
        hasMore: boolean;
      };
    }
  | {
      type: 'APPEND_MESSAGES';
      payload: {
        chatId: string;
        items: ChatMessage[];
        nextCursor: string | null;
        hasMore: boolean;
      };
    }
  | { type: 'ADD_MESSAGE'; payload: { chatId: string; item: ChatMessage } }
  | {
      type: 'UPDATE_CHAT_PARTIAL';
      payload: { chatId: string; patch: Partial<Chat> };
    };

const initialState: ChatState = {
  isLoading: false,
  error: null,
  chatsOrder: [],
  chatsById: {},
  messagesByChat: {},
  currentChatId: null,
};

function reducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload };
    case 'SET_ERROR':
      return { ...state, error: action.payload };
    case 'SET_CURRENT_CHAT':
      return { ...state, currentChatId: action.payload };

    case 'SET_CHATS': {
      const byId: Record<string, Chat> = {};
      const order: string[] = [];
      for (const c of action.payload) {
        byId[c.id] = c;
        order.push(c.id);
      }
      return { ...state, chatsById: byId, chatsOrder: order };
    }

    case 'UPSERT_CHAT': {
      const id = action.payload.id;
      const exists = !!state.chatsById[id];
      const chatsById = {
        ...state.chatsById,
        [id]: { ...state.chatsById[id], ...action.payload },
      };
      const chatsOrder = exists ? state.chatsOrder : [id, ...state.chatsOrder];
      return { ...state, chatsById, chatsOrder };
    }

    case 'DELETE_CHAT': {
      const { [action.payload]: _omitted, ...rest } = state.chatsById;
      void _omitted; // Suppress unused variable warning
      return {
        ...state,
        chatsById: rest,
        chatsOrder: state.chatsOrder.filter(id => id !== action.payload),
      };
    }

    case 'SET_MESSAGES': {
      const { chatId, items, nextCursor, hasMore } = action.payload;
      const messagesByChat = {
        ...state.messagesByChat,
        [chatId]: { items, nextCursor, hasMore, loaded: true },
      };
      return { ...state, messagesByChat };
    }

    case 'APPEND_MESSAGES': {
      const { chatId, items, nextCursor, hasMore } = action.payload;
      const prev = state.messagesByChat[chatId] || {
        items: [],
        nextCursor: null,
        hasMore: false,
        loaded: false,
      };
      const merged = [...prev.items, ...items];
      return {
        ...state,
        messagesByChat: {
          ...state.messagesByChat,
          [chatId]: { items: merged, nextCursor, hasMore, loaded: true },
        },
      };
    }

    case 'ADD_MESSAGE': {
      const { chatId, item } = action.payload;
      const prev = state.messagesByChat[chatId] || {
        items: [],
        nextCursor: null,
        hasMore: false,
        loaded: false,
      };
      return {
        ...state,
        messagesByChat: {
          ...state.messagesByChat,
          [chatId]: { ...prev, items: [...prev.items, item], loaded: true },
        },
      };
    }

    case 'UPDATE_CHAT_PARTIAL': {
      const { chatId, patch } = action.payload;
      const chat = state.chatsById[chatId];
      if (!chat) return state;
      return {
        ...state,
        chatsById: { ...state.chatsById, [chatId]: { ...chat, ...patch } },
      };
    }
  }
}

type ChatContextValue = {
  state: ChatState;
  loadChats: () => Promise<void>;
  loadChatsIfAuthenticated: () => Promise<void>;
  createChat: (name?: string | null, tags?: string[] | null) => Promise<string>;
  renameChat: (chatId: string, name: string) => Promise<void>;
  deleteChat: (chatId: string) => Promise<void>;
  removeChatLocal: (chatId: string) => void;
  restoreChatLocal: (chat: Chat) => void;
  deleteChatApiOnly: (chatId: string) => Promise<void>;
  updateChatTags: (chatId: string, tags: string[]) => Promise<void>;
  setCurrentChat: (chatId: string | null) => void;
  loadMessages: (chatId: string, append?: boolean) => Promise<void>;
  sendMessage: (
    chatId: string,
    content: string,
    useRag?: boolean
  ) => Promise<string>;
  sendMessageStream: (
    chatId: string,
    content: string,
    onDelta: (chunk: string) => void,
    useRag?: boolean
  ) => Promise<void>;
};

const ChatContext = createContext<ChatContextValue | undefined>(undefined);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const bootRef = useRef(false);

  async function loadChats() {
    dispatch({ type: 'SET_LOADING', payload: true });
    try {
      const res = await chatsApi.listChats({ limit: 100 });
      dispatch({ type: 'SET_CHATS', payload: res.items });
      dispatch({ type: 'SET_ERROR', payload: null });
    } catch (e: any) {
      dispatch({
        type: 'SET_ERROR',
        payload: e?.message || 'failed_to_load_chats',
      });
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false });
    }
  }

  async function loadChatsIfAuthenticated() {
    const token =
      (window as any).__auth_tokens?.access_token ||
      localStorage.getItem('access_token');
    if (token) {
      await loadChats();
    }
  }

  useEffect(() => {
    if (bootRef.current) return;
    bootRef.current = true;
    loadChatsIfAuthenticated();
  }, []);

  async function createChat(name?: string | null, tags?: string[] | null) {
    const res = await chatsApi.createChat(name ?? null, tags ?? null);
    const chatId = res.chat_id;
    // optimistic
    dispatch({
      type: 'UPSERT_CHAT',
      payload: { id: chatId, name: name ?? null, tags: tags ?? null } as Chat,
    });
    return chatId;
  }

  async function renameChat(chatId: string, name: string) {
    await chatsApi.renameChat(chatId, name);
    dispatch({
      type: 'UPDATE_CHAT_PARTIAL',
      payload: { chatId, patch: { name } },
    });
  }

  async function deleteChat(chatId: string) {
    await chatsApi.deleteChat(chatId);
    dispatch({ type: 'DELETE_CHAT', payload: chatId });
    if (state.currentChatId === chatId)
      dispatch({ type: 'SET_CURRENT_CHAT', payload: null });
  }

  function removeChatLocal(chatId: string) {
    dispatch({ type: 'DELETE_CHAT', payload: chatId });
    if (state.currentChatId === chatId)
      dispatch({ type: 'SET_CURRENT_CHAT', payload: null });
  }

  function restoreChatLocal(chat: Chat) {
    dispatch({ type: 'UPSERT_CHAT', payload: chat });
  }

  async function deleteChatApiOnly(chatId: string) {
    await chatsApi.deleteChat(chatId);
  }

  async function updateChatTags(chatId: string, tags: string[]) {
    await chatsApi.updateChatTags(chatId, tags);
    dispatch({
      type: 'UPDATE_CHAT_PARTIAL',
      payload: { chatId, patch: { tags } },
    });
  }

  function setCurrentChat(chatId: string | null) {
    dispatch({ type: 'SET_CURRENT_CHAT', payload: chatId });
  }

  async function loadMessages(chatId: string, append?: boolean) {
    const cur = state.messagesByChat[chatId];
    if (!append && cur?.loaded) return; // avoid duplicate initial load
    const res = await chatsApi.listMessages(
      chatId,
      append ? { cursor: cur?.nextCursor || undefined } : {}
    );
    const items = res.items;
    const next = res.next_cursor ?? null;
    const hasMore = !!next && items.length > 0;
    dispatch({
      type: append ? 'APPEND_MESSAGES' : 'SET_MESSAGES',
      payload: { chatId, items, nextCursor: next, hasMore },
    });
  }

  async function sendMessage(
    chatId: string,
    content: string,
    useRag?: boolean
  ) {
    const res = await chatsApi.sendMessage(chatId, {
      content,
      use_rag: !!useRag,
    });
    const userMsg: ChatMessage = {
      id: res.id,
      chat_id: chatId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };
    dispatch({ type: 'ADD_MESSAGE', payload: { chatId, item: userMsg } });
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      chat_id: chatId,
      role: 'assistant',
      content: typeof res.content === 'string' ? res.content : JSON.stringify(res.content),
      created_at: res.created_at,
    };
    dispatch({ type: 'ADD_MESSAGE', payload: { chatId, item: assistantMsg } });
    return res.id;
  }

  async function sendMessageStream(
    chatId: string,
    content: string,
    onDelta: (chunk: string) => void,
    useRag?: boolean
  ) {
    // add user message immediately
    dispatch({
      type: 'ADD_MESSAGE',
      payload: {
        chatId,
        item: {
          id: crypto.randomUUID(),
          chat_id: chatId,
          role: 'user',
          content,
        },
      },
    });
    let acc = '';
    for await (const chunk of chatsApi.sendMessageStream(chatId, {
      content,
      use_rag: !!useRag,
    })) {
      acc += chunk;
      onDelta(acc);
    }
    // push final assistant message
    dispatch({
      type: 'ADD_MESSAGE',
      payload: {
        chatId,
        item: {
          id: crypto.randomUUID(),
          chat_id: chatId,
          role: 'assistant',
          content: acc,
        },
      },
    });
  }

  const value: ChatContextValue = {
    state,
    loadChats,
    loadChatsIfAuthenticated,
    createChat,
    renameChat,
    deleteChat,
    removeChatLocal,
    restoreChatLocal,
    deleteChatApiOnly,
    updateChatTags,
    setCurrentChat,
    loadMessages,
    sendMessage,
    sendMessageStream,
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChat must be used within ChatProvider');
  return ctx;
}
