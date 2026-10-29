import { create } from 'zustand';

interface ChatNotificationsState {
  userId: string | null;
  activeChatId: string | null;
  unreadChatIds: Record<string, boolean>;
  setActiveChat: (chatId: string | null) => void;
  receiveCompleted: (chatId: string) => boolean;
  reset: (userId?: string | null) => void;
}

/** Session-local presentation state; execution statuses remain in the query cache. */
export const useChatNotificationsStore = create<ChatNotificationsState>(
  (set, get) => ({
    userId: null,
    activeChatId: null,
    unreadChatIds: {},
    setActiveChat: chatId =>
      set(state => {
        const unreadChatIds = { ...state.unreadChatIds };
        if (chatId) delete unreadChatIds[chatId];
        return { activeChatId: chatId, unreadChatIds };
      }),
    receiveCompleted: chatId => {
      if (get().activeChatId === chatId) return false;
      set(state => ({
        unreadChatIds: { ...state.unreadChatIds, [chatId]: true },
      }));
      return true;
    },
    reset: (userId = null) => set({ userId, unreadChatIds: {} }),
  })
);
