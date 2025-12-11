import React, { useEffect, useMemo, useRef } from 'react';
import styles from './Chat.module.css';
import { useNavigate, useParams } from 'react-router-dom';
import { useChat } from '@/domains/chat/contexts/ChatContext';
import EmptyState from '@shared/ui/EmptyState';
import Button from '@shared/ui/Button';
import { ChatMessage } from '@/domains/chat/components/ChatMessage';
import { ChatComposer } from '@/domains/chat/components/ChatComposer';
import { Icon } from '@/shared/ui/Icon';

export default function Chat() {
  const { chatId } = useParams();
  const nav = useNavigate();
  const { state, loadMessages, setCurrentChat, sendMessageStream } = useChat();
  const historyRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = React.useState(false);
  const [streamError, setStreamError] = React.useState<string | null>(null);

  const current = useMemo(
    () => (chatId ? state.messagesByChat[chatId] : undefined),
    [chatId, state.messagesByChat]
  );
  const messages = current?.items || [];

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    if (historyRef.current) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages.length]);

  useEffect(() => {
    if (!chatId) return;
    setCurrentChat(chatId);
    if (!state.messagesByChat[chatId]?.loaded) {
      loadMessages(chatId).catch(console.error);
    }
    setBusy(false);
    setStreamError(null);
  }, [chatId]);

  // Normalize content
  const normalizeContent = (content: any): string => {
    if (typeof content === 'string') return content;
    if (typeof content === 'object' && content?.text) return content.text;
    return String(content || '');
  };

  // Handle send with agent support
  const handleSend = async (
    message: string,
    options: { agentSlug?: string; attachments?: File[] }
  ) => {
    if (!chatId) return;
    setBusy(true);
    setStreamError(null);

    // Determine if RAG should be used based on agent
    const useRag = options.agentSlug === 'chat-rag';

    try {
      await sendMessageStream(
        chatId,
        message,
        useRag,
        () => {},
        (err: string) => setStreamError(err),
        options.agentSlug
      );
    } catch (e: any) {
      console.error(e);
      setStreamError(e?.message || 'Ошибка при отправке сообщения');
    } finally {
      setBusy(false);
    }
  };

  // Empty state
  if (!chatId) {
    return (
      <div className={styles.emptyContainer}>
        <div className={styles.emptyContent}>
          <div className={styles.emptyIcon}>
            <Icon name="sparkles" size={48} />
          </div>
          <h2 className={styles.emptyTitle}>Добро пожаловать в ML Portal Chat</h2>
          <p className={styles.emptyDescription}>
            Выберите существующий чат слева или создайте новый, чтобы начать общение с AI-ассистентом.
          </p>
          <div className={styles.emptyFeatures}>
            <div className={styles.feature}>
              <Icon name="sparkles" size={20} />
              <span>Умный ассистент</span>
            </div>
            <div className={styles.feature}>
              <Icon name="database" size={20} />
              <span>Поиск по базе знаний</span>
            </div>
            <div className={styles.feature}>
              <Icon name="file" size={20} />
              <span>Работа с файлами</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Get last message for streaming indicator
  const lastMessage = messages[messages.length - 1];
  const isStreaming = lastMessage?.role === 'assistant' && lastMessage?.isOptimistic;

  return (
    <div className={styles.chatContainer}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerInfo}>
          <h2 className={styles.headerTitle}>Чат</h2>
          {state.streamStatus && (
            <span className={styles.streamStatus}>{state.streamStatus}</span>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className={styles.messagesContainer} ref={historyRef}>
        {messages.length === 0 && !state.isLoading ? (
          <div className={styles.noMessages}>
            <Icon name="sparkles" size={32} />
            <p>Начните диалог, отправив сообщение</p>
          </div>
        ) : (
          messages.map((m, idx) => (
            <ChatMessage
              key={m.id}
              id={m.id}
              role={m.role}
              content={normalizeContent(m.content)}
              createdAt={m.created_at}
              isStreaming={m.role === 'assistant' && idx === messages.length - 1 && isStreaming}
              ragSources={m.meta?.rag_sources}
            />
          ))
        )}

        {/* Error message */}
        {streamError && (
          <div className={styles.errorBanner}>
            <Icon name="x" size={16} />
            <span>{streamError}</span>
          </div>
        )}
      </div>

      {/* Composer */}
      <ChatComposer
        onSend={handleSend}
        disabled={busy}
        placeholder="Напишите сообщение..."
      />
    </div>
  );
}
