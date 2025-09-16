import React, { memo, useMemo } from 'react';
import { ChatMessage } from '../store/useChatStore';
import styles from './OptimizedChatMessage.module.css';

interface OptimizedChatMessageProps {
  message: ChatMessage;
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

    return (
      <div className={messageClass}>
        <div className={styles.messageContent}>{messageContent}</div>
        {messageTime && <div className={styles.messageTime}>{messageTime}</div>}
      </div>
    );
  }
);

OptimizedChatMessage.displayName = 'OptimizedChatMessage';

export default OptimizedChatMessage;
