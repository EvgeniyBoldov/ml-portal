import React, { memo, useMemo } from 'react';
import { ChatMessage } from '@/shared/api/types';
import styles from './OptimizedChatMessage.module.css';
import MarkdownMessage from './MarkdownMessage';
import RAGSources from './RAGSources';

interface OptimizedChatMessageProps {
  message: ChatMessage & { meta?: Record<string, unknown> };
  index: number;
}

const OptimizedChatMessage = memo<OptimizedChatMessageProps>(({ message, index: _index }) => {
  const messageContent = useMemo(() => message.content, [message.content]);

  const messageTime = useMemo(() => {
    if (!message.created_at) return null;
    const date = new Date(message.created_at);
    if (Number.isNaN(date.getTime())) return null;
    return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  }, [message.created_at]);

  const messageClass = useMemo(() => {
    return message.role === 'user' ? styles.user : styles.assistant;
  }, [message.role]);

  return (
    <div className={`${styles.message} ${messageClass}`}>
      <div className={styles.avatar}>
        {message.role === 'user' ? 'U' : 'A'}
      </div>
      <div className={styles.content}>
        <div className={styles.header}>
          <span className={styles.role}>{message.role === 'user' ? 'User' : 'Assistant'}</span>
          <span className={styles.time}>{messageTime}</span>
        </div>
        <div className={styles.body}>
          <div className={styles.userText}>{messageContent}</div>
        </div>
      </div>
    </div>
  );
});

OptimizedChatMessage.displayName = 'OptimizedChatMessage';
export default OptimizedChatMessage;
