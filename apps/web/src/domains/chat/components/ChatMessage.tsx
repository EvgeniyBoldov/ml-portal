import { useState, memo } from 'react';
import MarkdownRenderer from '@/shared/ui/MarkdownRenderer';
import { Icon } from '@/shared/ui/Icon';
import styles from './ChatMessage.module.css';

interface ChatMessageProps {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt?: string;
  isStreaming?: boolean;
  ragSources?: Array<{ title: string; source_id: string; score: number }>;
  attachments?: Array<{ name: string; type: string; url?: string }>;
}

function ChatMessageComponent({
  id,
  role,
  content,
  createdAt,
  isStreaming,
  ragSources,
  attachments,
}: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const [showSources, setShowSources] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const formatTime = (dateStr?: string) => {
    if (!dateStr) return '';
    try {
      // Handle both ISO strings and timestamps
      const date = typeof dateStr === 'number' ? new Date(dateStr) : new Date(dateStr);
      if (isNaN(date.getTime())) return '';
      return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const isUser = role === 'user';

  return (
    <div className={`${styles.message} ${isUser ? styles.user : styles.assistant}`}>
      {/* Avatar */}
      <div className={styles.avatar}>
        {isUser ? (
          <Icon name="user" size={20} />
        ) : (
          <Icon name="bot" size={20} />
        )}
      </div>

      {/* Content */}
      <div className={styles.content}>
        <div className={styles.header}>
          <span className={styles.role}>{isUser ? 'Вы' : 'Ассистент'}</span>
          {createdAt && <span className={styles.time}>{formatTime(createdAt)}</span>}
        </div>

        {/* Attachments */}
        {attachments && attachments.length > 0 && (
          <div className={styles.attachments}>
            {attachments.map((file, idx) => (
              <div key={idx} className={styles.attachment}>
                <Icon name="file" size={14} />
                <span>{file.name}</span>
              </div>
            ))}
          </div>
        )}

        {/* Message body */}
        <div className={styles.body}>
          {isUser ? (
            <div className={styles.userText}>{content}</div>
          ) : content ? (
            <MarkdownRenderer content={content} />
          ) : isStreaming ? (
            <div className={styles.typing}>
              <span></span>
              <span></span>
              <span></span>
            </div>
          ) : null}
        </div>

        {/* RAG Sources */}
        {ragSources && ragSources.length > 0 && (
          <div className={styles.sources}>
            <button
              className={styles.sourcesToggle}
              onClick={() => setShowSources(!showSources)}
            >
              <Icon name="file-text" size={14} />
              <span>{ragSources.length} источник{ragSources.length > 1 ? 'а' : ''}</span>
              <Icon name={showSources ? 'chevron-up' : 'chevron-down'} size={14} />
            </button>
            {showSources && (
              <div className={styles.sourcesList}>
                {ragSources.map((src, idx) => (
                  <div key={idx} className={styles.sourceItem}>
                    <Icon name="file" size={12} />
                    <span className={styles.sourceTitle}>{src.title}</span>
                    <span className={styles.sourceScore}>
                      {Math.round(src.score * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        {!isUser && content && !isStreaming && (
          <div className={styles.actions}>
            <button
              className={styles.actionBtn}
              onClick={handleCopy}
              title={copied ? 'Скопировано!' : 'Копировать'}
            >
              <Icon name={copied ? 'check' : 'copy'} size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export const ChatMessage = memo(ChatMessageComponent);
export default ChatMessage;
