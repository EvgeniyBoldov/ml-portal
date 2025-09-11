import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'
import { immer } from 'zustand/middleware/immer'

export interface ChatMessage {
  id?: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at?: string
  chat_id?: string
}

export interface Chat {
  id: string
  name?: string
  tags?: string[]
  created_at?: string
  updated_at?: string
  last_message_at?: string
  messages: ChatMessage[]
  isLoading?: boolean
  hasMore?: boolean
  nextCursor?: string | null
}

interface ChatState {
  chats: Record<string, Chat>
  currentChatId: string | null
  isLoading: boolean
  error: string | null
  searchQuery: string
  selectedTags: string[]
}

interface ChatActions {
  // Chat management
  addChat: (chat: Chat) => void
  updateChat: (chatId: string, updates: Partial<Chat>) => void
  deleteChat: (chatId: string) => void
  setCurrentChat: (chatId: string | null) => void
  
  // Messages
  addMessage: (chatId: string, message: ChatMessage) => void
  updateMessage: (chatId: string, messageId: string, updates: Partial<ChatMessage>) => void
  setMessages: (chatId: string, messages: ChatMessage[], hasMore: boolean, nextCursor: string | null) => void
  appendMessages: (chatId: string, messages: ChatMessage[], hasMore: boolean, nextCursor: string | null) => void
  
  // UI state
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  setSearchQuery: (query: string) => void
  setSelectedTags: (tags: string[]) => void
  
  // Bulk operations
  loadChats: (chats: Chat[]) => void
  clearError: () => void
  reset: () => void
}

type ChatStore = ChatState & ChatActions

const initialState: ChatState = {
  chats: {},
  currentChatId: null,
  isLoading: false,
  error: null,
  searchQuery: '',
  selectedTags: []
}

export const useChatStore = create<ChatStore>()(
  devtools(
    persist(
      immer((set, get) => ({
        ...initialState,
        
        // Chat management
        addChat: (chat) => set((state) => {
          state.chats[chat.id] = chat
        }),
        
        updateChat: (chatId, updates) => set((state) => {
          if (state.chats[chatId]) {
            Object.assign(state.chats[chatId], updates)
          }
        }),
        
        deleteChat: (chatId) => set((state) => {
          delete state.chats[chatId]
          if (state.currentChatId === chatId) {
            state.currentChatId = null
          }
        }),
        
        setCurrentChat: (chatId) => set((state) => {
          state.currentChatId = chatId
        }),
        
        // Messages
        addMessage: (chatId, message) => set((state) => {
          if (state.chats[chatId]) {
            state.chats[chatId].messages.push(message)
            state.chats[chatId].last_message_at = message.created_at || new Date().toISOString()
          }
        }),
        
        updateMessage: (chatId, messageId, updates) => set((state) => {
          if (state.chats[chatId]) {
            const messageIndex = state.chats[chatId].messages.findIndex(m => m.id === messageId)
            if (messageIndex !== -1) {
              Object.assign(state.chats[chatId].messages[messageIndex], updates)
            }
          }
        }),
        
        setMessages: (chatId, messages, hasMore, nextCursor) => set((state) => {
          if (state.chats[chatId]) {
            state.chats[chatId].messages = messages
            state.chats[chatId].hasMore = hasMore
            state.chats[chatId].nextCursor = nextCursor
            state.chats[chatId].isLoading = false
          }
        }),
        
        appendMessages: (chatId, messages, hasMore, nextCursor) => set((state) => {
          if (state.chats[chatId]) {
            state.chats[chatId].messages = [...messages, ...state.chats[chatId].messages]
            state.chats[chatId].hasMore = hasMore
            state.chats[chatId].nextCursor = nextCursor
            state.chats[chatId].isLoading = false
          }
        }),
        
        // UI state
        setLoading: (loading) => set((state) => {
          state.isLoading = loading
        }),
        
        setError: (error) => set((state) => {
          state.error = error
        }),
        
        setSearchQuery: (query) => set((state) => {
          state.searchQuery = query
        }),
        
        setSelectedTags: (tags) => set((state) => {
          state.selectedTags = tags
        }),
        
        // Bulk operations
        loadChats: (chats) => set((state) => {
          chats.forEach(chat => {
            state.chats[chat.id] = chat
          })
        }),
        
        clearError: () => set((state) => {
          state.error = null
        }),
        
        reset: () => set(() => initialState)
      })),
      {
        name: 'chat-store',
        partialize: (state) => ({
          chats: state.chats,
          currentChatId: state.currentChatId,
          searchQuery: state.searchQuery,
          selectedTags: state.selectedTags
        })
      }
    ),
    {
      name: 'chat-store'
    }
  )
)

// Selectors
export const useCurrentChat = () => useChatStore((state) => 
  state.currentChatId ? state.chats[state.currentChatId] : null
)

export const useChatMessages = (chatId: string) => useChatStore((state) => 
  state.chats[chatId]?.messages || []
)

export const useFilteredChats = () => useChatStore((state) => {
  const { chats, searchQuery, selectedTags } = state
  
  return Object.values(chats).filter(chat => {
    const matchesSearch = !searchQuery || 
      chat.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      chat.messages.some(msg => 
        msg.content.toLowerCase().includes(searchQuery.toLowerCase())
      )
    
    const matchesTags = selectedTags.length === 0 ||
      selectedTags.every(tag => chat.tags?.includes(tag))
    
    return matchesSearch && matchesTags
  }).sort((a, b) => 
    new Date(b.last_message_at || b.created_at || 0).getTime() - 
    new Date(a.last_message_at || a.created_at || 0).getTime()
  )
})

export const useChatStats = () => useChatStore((state) => {
  const chats = Object.values(state.chats)
  const totalMessages = chats.reduce((sum, chat) => sum + chat.messages.length, 0)
  const userMessages = chats.reduce((sum, chat) => 
    sum + chat.messages.filter(msg => msg.role === 'user').length, 0
  )
  const assistantMessages = chats.reduce((sum, chat) => 
    sum + chat.messages.filter(msg => msg.role === 'assistant').length, 0
  )
  
  return {
    totalChats: chats.length,
    totalMessages,
    userMessages,
    assistantMessages,
    averageMessagesPerChat: chats.length > 0 ? Math.round(totalMessages / chats.length) : 0
  }
})
