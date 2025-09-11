import React from 'react'
import { useChat } from '../contexts/ChatContext'
import styles from './ChatStatus.module.css'

export default function ChatStatus() {
  const { state } = useChat()
  const { error, isLoading } = state

  if (!error && !isLoading) return null

  return (
    <div className={styles.statusBar}>
      {isLoading && (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          Загрузка...
        </div>
      )}
      {error && (
        <div className={styles.error}>
          ⚠️ {error}
        </div>
      )}
    </div>
  )
}
