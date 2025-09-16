import React from 'react';
import styles from './ChatPage.module.css';
import ChatSidebar from './ChatSidebar';
import Chat from './Chat';
import { ChatProvider } from '../../contexts/ChatContext';
import ChatStatus from '../../components/ChatStatus';

export default function ChatPage() {
  return (
    <ChatProvider>
      <div className={styles.shell}>
        <ChatSidebar />
        <div className={styles.main}>
          <Chat />
        </div>
        <ChatStatus />
      </div>
    </ChatProvider>
  );
}
