import React, { createContext, useContext, useReducer, useEffect } from 'react'
import * as chats from '@shared/api/chats'

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
}

type ChatAction =
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_CURRENT_CHAT'; payload: string | null }
  | { type: 'ADD_CHAT'; payload: Chat }
  | { type: 'UPDATE_CHAT'; payload: { id: string; updates: Partial<Chat> } }
  | { type: 'DELETE_CHAT'; payload: string }
  | { type: 'ADD_MESSAGE'; payload: { chatId: string; message: ChatMessage } }
  | { type: 'UPDATE_MESSAGE'; payload: { chatId: string; messageId: string; updates: Partial<ChatMessage> } }
  | { type: 'SET_MESSAGES'; payload: { chatId: string; messages: ChatMessage[]; hasMore: boolean; nextCursor: string | null } }
  | { type: 'APPEND_MESSAGES'; payload: { chatId: string; messages: ChatMessage[]; hasMore: boolean; nextCursor: string | null } }

const initialState: ChatState = {
  chats: {},
  currentChatId: null,
  isLoading: false,
  error: null
}

function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload }
    
    case 'SET_ERROR':
      return { ...state, error: action.payload }
    
    case 'SET_CURRENT_CHAT':
      return { ...state, currentChatId: action.payload }
    
    case 'ADD_CHAT':
      return {
        ...state,
        chats: {
          ...state.chats,
          [action.payload.id]: action.payload
        }
      }
    
    case 'UPDATE_CHAT':
      return {
        ...state,
        chats: {
          ...state.chats,
          [action.payload.id]: {
            ...state.chats[action.payload.id],
            ...action.payload.updates
          }
        }
      }
    
    case 'DELETE_CHAT':
      const { [action.payload]: deleted, ...remainingChats } = state.chats
      return {
        ...state,
        chats: remainingChats,
        currentChatId: state.currentChatId === action.payload ? null : state.currentChatId
      }
    
    case 'ADD_MESSAGE':
      const chat = state.chats[action.payload.chatId]
      if (!chat) return state
      
      return {
        ...state,
        chats: {
          ...state.chats,
          [action.payload.chatId]: {
            ...chat,
            messages: [...chat.messages, action.payload.message],
            last_message_at: action.payload.message.created_at || new Date().toISOString()
          }
        }
      }
    
    case 'UPDATE_MESSAGE':
      const chatToUpdate = state.chats[action.payload.chatId]
      if (!chatToUpdate) return state
      
      return {
        ...state,
        chats: {
          ...state.chats,
          [action.payload.chatId]: {
            ...chatToUpdate,
            messages: chatToUpdate.messages.map(msg =>
              msg.id === action.payload.messageId
                ? { ...msg, ...action.payload.updates }
                : msg
            )
          }
        }
      }
    
    case 'SET_MESSAGES':
      return {
        ...state,
        chats: {
          ...state.chats,
          [action.payload.chatId]: {
            ...state.chats[action.payload.chatId],
            messages: action.payload.messages,
            hasMore: action.payload.hasMore,
            nextCursor: action.payload.nextCursor,
            isLoading: false
          }
        }
      }
    
    case 'APPEND_MESSAGES':
      const existingChat = state.chats[action.payload.chatId]
      if (!existingChat) return state
      
      return {
        ...state,
        chats: {
          ...state.chats,
          [action.payload.chatId]: {
            ...existingChat,
            messages: [...action.payload.messages, ...existingChat.messages],
            hasMore: action.payload.hasMore,
            nextCursor: action.payload.nextCursor,
            isLoading: false
          }
        }
      }
    
    default:
      return state
  }
}

interface ChatContextType {
  state: ChatState
  dispatch: React.Dispatch<ChatAction>
  // Actions
  createChat: (name?: string, tags?: string[]) => Promise<string>
  loadChats: () => Promise<void>
  loadMessages: (chatId: string, loadMore?: boolean) => Promise<void>
  sendMessage: (chatId: string, content: string, useRag?: boolean) => Promise<void>
  sendMessageStream: (chatId: string, content: string, useRag?: boolean) => Promise<void>
  renameChat: (chatId: string, name: string) => Promise<void>
  updateChatTags: (chatId: string, tags: string[]) => Promise<void>
  deleteChat: (chatId: string) => Promise<void>
  setCurrentChat: (chatId: string | null) => void
}

const ChatContext = createContext<ChatContextType | undefined>(undefined)

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(chatReducer, initialState)

  const createChat = async (name?: string, tags?: string[]): Promise<string> => {
    try {
      dispatch({ type: 'SET_LOADING', payload: true })
      const { chat_id } = await chats.createChat(name, tags)
      
      const newChat: Chat = {
        id: chat_id,
        name: name || 'Новый чат',
        tags: tags || [],
        messages: [],
        hasMore: false,
        nextCursor: null,
        created_at: new Date().toISOString()
      }
      
      dispatch({ type: 'ADD_CHAT', payload: newChat })
      dispatch({ type: 'SET_CURRENT_CHAT', payload: chat_id })
      
      return chat_id
    } catch (error) {
      dispatch({ type: 'SET_ERROR', payload: 'Ошибка создания чата' })
      throw error
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false })
    }
  }

  const loadChats = async (): Promise<void> => {
    try {
      dispatch({ type: 'SET_LOADING', payload: true })
      const res = await chats.listChats({ limit: 100 })
      
      const chatsList = (res.items || []).map((item: any) => ({
        id: item.id || item.chat_id,
        name: item.name || 'Untitled',
        tags: item.tags || [],
        created_at: item.created_at,
        updated_at: item.updated_at,
        last_message_at: item.last_message_at,
        messages: [],
        hasMore: true,
        nextCursor: null
      }))
      
      chatsList.forEach(chat => {
        dispatch({ type: 'ADD_CHAT', payload: chat })
      })
    } catch (error) {
      dispatch({ type: 'SET_ERROR', payload: 'Ошибка загрузки чатов' })
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false })
    }
  }

  const loadMessages = async (chatId: string, loadMore = false): Promise<void> => {
    try {
      dispatch({ type: 'UPDATE_CHAT', payload: { id: chatId, updates: { isLoading: true } } })
      
      const chat = state.chats[chatId]
      const cursor = loadMore ? chat?.nextCursor : undefined
      
      const res = await chats.listMessages(chatId, { 
        limit: 50, 
        cursor 
      })
      
      const messages = (res.items || []).map((msg: any) => ({
        id: msg.id || msg.message_id,
        role: msg.role,
        content: msg.content,
        created_at: msg.created_at,
        chat_id: chatId
      }))
      
      if (loadMore) {
        dispatch({ 
          type: 'APPEND_MESSAGES', 
          payload: { 
            chatId, 
            messages, 
            hasMore: !!res.next_cursor, 
            nextCursor: res.next_cursor 
          } 
        })
      } else {
        dispatch({ 
          type: 'SET_MESSAGES', 
          payload: { 
            chatId, 
            messages, 
            hasMore: !!res.next_cursor, 
            nextCursor: res.next_cursor 
          } 
        })
      }
    } catch (error) {
      dispatch({ type: 'SET_ERROR', payload: 'Ошибка загрузки сообщений' })
    }
  }

  const sendMessage = async (chatId: string, content: string, useRag = false): Promise<void> => {
    try {
      // Добавляем сообщение пользователя
      const userMessage: ChatMessage = {
        role: 'user',
        content,
        chat_id: chatId,
        created_at: new Date().toISOString()
      }
      dispatch({ type: 'ADD_MESSAGE', payload: { chatId, message: userMessage } })
      
      // Отправляем сообщение
      const res = await chats.sendMessage(chatId, { content, use_rag: useRag, response_stream: false })
      const answer = (res && (res.answer || res.content || res.message || '')) as string
      
      // Добавляем ответ ассистента
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: answer,
        chat_id: chatId,
        created_at: new Date().toISOString()
      }
      dispatch({ type: 'ADD_MESSAGE', payload: { chatId, message: assistantMessage } })
    } catch (error) {
      dispatch({ type: 'SET_ERROR', payload: 'Ошибка отправки сообщения' })
      throw error
    }
  }

  const sendMessageStream = async (chatId: string, content: string, useRag = false): Promise<void> => {
    try {
      // Добавляем сообщение пользователя
      const userMessage: ChatMessage = {
        role: 'user',
        content,
        chat_id: chatId,
        created_at: new Date().toISOString()
      }
      dispatch({ type: 'ADD_MESSAGE', payload: { chatId, message: userMessage } })
      
      // Добавляем плейсхолдер для ответа
      const assistantMessageId = `temp_${Date.now()}`
      const assistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        chat_id: chatId,
        created_at: new Date().toISOString()
      }
      dispatch({ type: 'ADD_MESSAGE', payload: { chatId, message: assistantMessage } })
      
      // Отправляем сообщение с потоком
      let fullContent = ''
      for await (const chunk of chats.sendMessageStream(chatId, { content, use_rag: useRag })) {
        fullContent += String(chunk || '')
        dispatch({ 
          type: 'UPDATE_MESSAGE', 
          payload: { 
            chatId, 
            messageId: assistantMessageId, 
            updates: { content: fullContent } 
          } 
        })
      }
    } catch (error) {
      dispatch({ type: 'SET_ERROR', payload: 'Ошибка отправки сообщения' })
      throw error
    }
  }

  const renameChat = async (chatId: string, name: string): Promise<void> => {
    try {
      await chats.renameChat(chatId, name)
      dispatch({ type: 'UPDATE_CHAT', payload: { id: chatId, updates: { name } } })
    } catch (error) {
      dispatch({ type: 'SET_ERROR', payload: 'Ошибка переименования чата' })
      throw error
    }
  }

  const updateChatTags = async (chatId: string, tags: string[]): Promise<void> => {
    try {
      await chats.updateChatTags(chatId, tags)
      dispatch({ type: 'UPDATE_CHAT', payload: { id: chatId, updates: { tags } } })
    } catch (error) {
      dispatch({ type: 'SET_ERROR', payload: 'Ошибка обновления тегов' })
      throw error
    }
  }

  const deleteChat = async (chatId: string): Promise<void> => {
    try {
      await chats.deleteChat(chatId)
      dispatch({ type: 'DELETE_CHAT', payload: chatId })
    } catch (error) {
      dispatch({ type: 'SET_ERROR', payload: 'Ошибка удаления чата' })
      throw error
    }
  }

  const setCurrentChat = (chatId: string | null): void => {
    dispatch({ type: 'SET_CURRENT_CHAT', payload: chatId })
  }

  // Загружаем чаты при инициализации
  useEffect(() => {
    loadChats()
  }, [])

  const value: ChatContextType = {
    state,
    dispatch,
    createChat,
    loadChats,
    loadMessages,
    sendMessage,
    sendMessageStream,
    renameChat,
    updateChatTags,
    deleteChat,
    setCurrentChat
  }

  return (
    <ChatContext.Provider value={value}>
      {children}
    </ChatContext.Provider>
  )
}

export function useChat() {
  const context = useContext(ChatContext)
  if (context === undefined) {
    throw new Error('useChat must be used within a ChatProvider')
  }
  return context
}
