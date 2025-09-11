import React from 'react'
import { useChat } from '../contexts/ChatContext'
import styles from './ChatStats.module.css'

export default function ChatStats() {
  const { state } = useChat()
  const { chats } = state

  const stats = React.useMemo(() => {
    const chatList = Object.values(chats)
    const totalMessages = chatList.reduce((sum, chat) => sum + chat.messages.length, 0)
    const userMessages = chatList.reduce((sum, chat) => 
      sum + chat.messages.filter(msg => msg.role === 'user').length, 0
    )
    const assistantMessages = chatList.reduce((sum, chat) => 
      sum + chat.messages.filter(msg => msg.role === 'assistant').length, 0
    )
    
    const totalWords = chatList.reduce((sum, chat) => 
      sum + chat.messages.reduce((msgSum, msg) => 
        msgSum + msg.content.split(' ').length, 0
      ), 0
    )

    const averageMessagesPerChat = chatList.length > 0 ? Math.round(totalMessages / chatList.length) : 0
    const averageWordsPerMessage = totalMessages > 0 ? Math.round(totalWords / totalMessages) : 0

    return {
      totalChats: chatList.length,
      totalMessages,
      userMessages,
      assistantMessages,
      totalWords,
      averageMessagesPerChat,
      averageWordsPerMessage
    }
  }, [chats])

  return (
    <div className={styles.statsContainer}>
      <h4 className={styles.statsTitle}>Статистика чатов</h4>
      
      <div className={styles.statsGrid}>
        <div className={styles.statItem}>
          <div className={styles.statValue}>{stats.totalChats}</div>
          <div className={styles.statLabel}>Всего чатов</div>
        </div>
        
        <div className={styles.statItem}>
          <div className={styles.statValue}>{stats.totalMessages}</div>
          <div className={styles.statLabel}>Всего сообщений</div>
        </div>
        
        <div className={styles.statItem}>
          <div className={styles.statValue}>{stats.userMessages}</div>
          <div className={styles.statLabel}>Сообщений пользователя</div>
        </div>
        
        <div className={styles.statItem}>
          <div className={styles.statValue}>{stats.assistantMessages}</div>
          <div className={styles.statLabel}>Ответов ассистента</div>
        </div>
        
        <div className={styles.statItem}>
          <div className={styles.statValue}>{stats.totalWords.toLocaleString()}</div>
          <div className={styles.statLabel}>Всего слов</div>
        </div>
        
        <div className={styles.statItem}>
          <div className={styles.statValue}>{stats.averageMessagesPerChat}</div>
          <div className={styles.statLabel}>Среднее сообщений на чат</div>
        </div>
        
        <div className={styles.statItem}>
          <div className={styles.statValue}>{stats.averageWordsPerMessage}</div>
          <div className={styles.statLabel}>Среднее слов на сообщение</div>
        </div>
      </div>
    </div>
  )
}
