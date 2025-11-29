import React, { memo, useMemo } from 'react';
import { ChatMessage } from '@shared/api/types';
import styles from './OptimizedChatMessage.module.css';
import MarkdownMessage from './MarkdownMessage';
import RAGSources from './RAGSources';

interface OptimizedChatMessageProps {
  message: ChatMessage & { meta?: any };
  index: number;
}

const OptimizedChatMessage = memo<OptimizedChatMessageProps>(
  ({ message, index: _index }) => {
    const messageContent = useMemo(() => {
      return message.content;
    }, [message.content]);

    const messageTime = useMemo(() => {
      return message.created_at
        ? new Date(message.created_at).toLocaleTimeString()
        : null;
    }, [message.created_at]);

    const messageClass = useMemo(() => {
      return message.role === 'user' ? styles.user : styles.assistant;
    }, [message.role]);

    const ragSources = useMemo(() => {
      return message.meta?.rag_sources;
    }, [message.meta]);

    return (
      <div className={messageClass}>
        <div className={styles.messageContent}>
          <MarkdownMessage content={messageContent} />
          {ragSources && <RAGSources sources={ragSources} />}
        </div>
        {messageTime && <div className={styles.messageTime}>{messageTime}</div>}
      </div>
    );
  }
);

OptimizedChatMessage.displayName = 'OptimizedChatMessage';

export default OptimizedChatMessage;
