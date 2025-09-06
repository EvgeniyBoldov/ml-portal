import React from 'react'
import styles from './ChatPage.module.css'
import ChatSidebar from './ChatSidebar'
import Chat from './Chat'

export default function ChatPage() {
  return (
    <div className={styles.shell}>
      <ChatSidebar />
      <div className={styles.main}>
        <Chat />
      </div>
    </div>
  )
}
