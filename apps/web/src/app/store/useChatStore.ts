import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

/**
 * useChatStore - Pure UI state for chats
 * Server state (chats list, messages) managed by TanStack Query
 * This store only holds:
 * - currentChatId: selected chat
 * - searchQuery: filter for chat list
 * - selectedTags: filter for chat list
 * - UI flags: sidebar collapsed, etc.
 */

interface ChatUIState {
  // Selection
  currentChatId: string | null;
  
  // Filters
  searchQuery: string;
  selectedTags: string[];
  
  // UI state
  isSidebarCollapsed: boolean;
}

interface ChatUIActions {
  // Selection
  setCurrentChat: (chatId: string | null) => void;
  
  // Filters
  setSearchQuery: (query: string) => void;
  setSelectedTags: (tags: string[]) => void;
  
  // UI state
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  
  // Reset
  reset: () => void;
}

type ChatStore = ChatUIState & ChatUIActions;

const initialState: ChatUIState = {
  currentChatId: null,
  searchQuery: '',
  selectedTags: [],
  isSidebarCollapsed: false,
};

export const useChatStore = create<ChatStore>()(
  devtools(
    persist(
      (set) => ({
        ...initialState,

        // Selection
        setCurrentChat: (chatId) =>
          set({ currentChatId: chatId }),

        // Filters
        setSearchQuery: (query) =>
          set({ searchQuery: query }),

        setSelectedTags: (tags) =>
          set({ selectedTags: tags }),

        // UI state
        toggleSidebar: () =>
          set((state) => ({ isSidebarCollapsed: !state.isSidebarCollapsed })),

        setSidebarCollapsed: (collapsed) =>
          set({ isSidebarCollapsed: collapsed }),

        // Reset
        reset: () => set(initialState),
      }),
      {
        name: 'chat-ui-store',
        partialize: (state) => ({
          currentChatId: state.currentChatId,
          isSidebarCollapsed: state.isSidebarCollapsed,
        }),
      }
    )
  )
);
