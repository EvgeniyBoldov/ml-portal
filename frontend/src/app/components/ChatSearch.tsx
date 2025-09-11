import React, { useState, useMemo } from 'react'
import { useChat } from '../contexts/ChatContext'
import Input from '@shared/ui/Input'
import styles from './ChatSearch.module.css'

export default function ChatSearch() {
  const { state } = useChat()
  const [searchQuery, setSearchQuery] = useState('')
  
  const filteredChats = useMemo(() => {
    if (!searchQuery.trim()) return Object.values(state.chats)
    
    const query = searchQuery.toLowerCase()
    return Object.values(state.chats).filter(chat => 
      chat.name?.toLowerCase().includes(query) ||
      chat.messages.some(msg => 
        msg.content.toLowerCase().includes(query)
      )
    )
  }, [state.chats, searchQuery])

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
          {filteredChats.map(chat => (
            <div key={chat.id} className={styles.chatResult}>
              <div className={styles.chatName}>{chat.name || 'Untitled'}</div>
              <div className={styles.chatPreview}>
                {chat.messages.length > 0 
                  ? chat.messages[chat.messages.length - 1].content.slice(0, 100) + '...'
                  : 'Нет сообщений'
                }
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
