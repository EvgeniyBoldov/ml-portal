import React, { useState, useMemo } from 'react'
import { useChat } from '../contexts/ChatContext'
import Input from '@shared/ui/Input'
import styles from './ChatSearch.module.css'

export default function ChatSearch() {
  const { state } = useChat()
  const [searchQuery, setSearchQuery] = useState('')
  
  const filteredChats = useMemo(() => {
    if (!searchQuery.trim()) return state.chatsOrder.map(id => state.chatsById[id])
    
    const query = searchQuery.toLowerCase()
    return state.chatsOrder.map(id => state.chatsById[id]).filter(chat => 
      chat.name?.toLowerCase().includes(query) ||
      (state.messagesByChat[chat.id]?.items || []).some(msg => 
        msg.content.toLowerCase().includes(query)
      )
    )
  }, [state.chatsOrder, state.chatsById, state.messagesByChat, searchQuery])

  return (
    <div className={styles.searchContainer}>
      <Input
        value={searchQuery}
        onChange={e => setSearchQuery(e.target.value)}
        placeholder="Поиск по чатам и сообщениям..."
        className={styles.searchInput}
      />
      {searchQuery && (
        <div className={styles.searchResults}>
          <div className={styles.resultsHeader}>
            Найдено чатов: {filteredChats.length}
          </div>
          {filteredChats.map(chat => {
            const messages = state.messagesByChat[chat.id]?.items || []
            return (
              <div key={chat.id} className={styles.chatResult}>
                <div className={styles.chatName}>{chat.name || 'Untitled'}</div>
                <div className={styles.chatPreview}>
                  {messages.length > 0 
                    ? messages[messages.length - 1].content.slice(0, 100) + '...'
                    : 'Нет сообщений'
                  }
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
