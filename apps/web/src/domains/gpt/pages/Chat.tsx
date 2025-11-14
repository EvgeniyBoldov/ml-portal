import React, { useEffect, useMemo, useState, useRef } from 'react';
import styles from './Chat.module.css';
import Card from '@shared/ui/Card';
import Button from '@shared/ui/Button';
import Textarea from '@shared/ui/Textarea';
import MarkdownRenderer from '@shared/ui/MarkdownRenderer';
import { useNavigate, useParams } from 'react-router-dom';
import { useChat } from '@/domains/chat/contexts/ChatContext';
import EmptyState from '@shared/ui/EmptyState';
import { useThrottle } from '@shared/hooks/useThrottle';

export default function Chat() {
  const { chatId } = useParams();
  const nav = useNavigate();
  const { state, loadMessages, setCurrentChat, sendMessageStream } = useChat();

  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [useRag, setUseRag] = useState(false);
  const [streamText, setStreamText] = useState('');
  const [streamError, setStreamError] = useState<string | null>(null);

  // Throttled версия setStreamText для плавности
  const throttledSetStreamText = useThrottle(setStreamText, 16); // ~60fps

  // Ref для контейнера истории сообщений
  const historyRef = useRef<HTMLDivElement>(null);

  const current = useMemo(
    () => (chatId ? state.messagesByChat[chatId] : undefined),
    [chatId, state.messagesByChat]
  );
  const messages = current?.items || [];

  // Функция для автоскролла вниз
  const scrollToBottom = () => {
    if (historyRef.current) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  };

  // Автоскролл при изменении сообщений или стрима
  useEffect(() => {
    scrollToBottom();
  }, [messages.length, streamText]);

  useEffect(() => {
    if (!chatId) return;
    setCurrentChat(chatId);
    // load once
    if (!state.messagesByChat[chatId]?.loaded) {
      loadMessages(chatId).catch(console.error);
    }
    // cleanup stream text on chat switch
    setStreamText('');
  }, [chatId]);

  if (!chatId) {
    return (
      <div className={styles.main}>
        <EmptyState
          title="Выберите чат"
          description="Слева — список ваших чатов. Создайте новый или откройте существующий."
          action={<Button onClick={() => nav('/gpt/chat')}>Обновить</Button>}
        />
      </div>
    );
  }

  async function onSend() {
    if (!text.trim()) return;
    setBusy(true);
    setStreamText('');
    setStreamError(null);
    const toSend = text;
    setText('');
    try {
      await sendMessageStream(
        chatId || '',
        toSend,
        useRag,
        delta => throttledSetStreamText(delta),
        (err: string) => setStreamError(err)
      );
    } catch (e: any) {
      console.error(e);
      setStreamError(e?.message || 'Ошибка при отправке сообщения');
    } finally {
      setBusy(false);
      setStreamText('');
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (canSend) {
        onSend();
      }
    }
  }

  const canSend = !!chatId && !!text.trim() && !busy;

  // Normalize content - extract text from object if needed
  const normalizeContent = (content: any): string => {
    if (typeof content === 'string') return content;
    if (typeof content === 'object' && content?.text) return content.text;
    return String(content || '');
  };

  return (
    <div className={styles.main}>
      <Card className={styles.card}>
        <div className={styles.history} ref={historyRef}>
          {messages.map(m => {
            const contentText = normalizeContent(m.content);
            return (
              <div
                key={m.id}
                className={
                  m.role === 'user' ? styles.userMsg : styles.assistantMsg
                }
              >
                <div className={styles.body}>
                  {m.role === 'assistant' ? (
                    <MarkdownRenderer content={contentText} />
                  ) : (
                    contentText
                  )}
                </div>
              </div>
            );
          })}
          {streamText && (
            <div className={styles.assistantMsg}>
              <div className={styles.body}>
                <MarkdownRenderer
                  content={streamText}
                  enableSyntaxHighlighting={false}
                />
              </div>
            </div>
          )}
          {messages.length === 0 && !state.isLoading && !streamText && (
            <div style={{ opacity: 0.7 }}>Сообщений пока нет.</div>
          )}
          {streamError && (
            <div className={styles.errorMsg}>
              <strong>Ошибка:</strong> {streamError}
            </div>
          )}
        </div>

        <div className={styles.composer}>
          <Textarea
            placeholder="Ваше сообщение… (Enter для отправки, Shift+Enter для новой строки)"
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!chatId || busy}
            rows={3}
          />
          <div className={styles.controls}>
            <div />
            <div className={styles.actionsBottom}>
              <Button onClick={onSend} disabled={!canSend}>
                Отправить
              </Button>
              <label
                className={styles.ragToggle}
                title="Использовать базу знаний (RAG) при ответе"
              >
                <input
                  type="checkbox"
                  checked={useRag}
                  onChange={e => setUseRag(e.target.checked)}
                />
                RAG из БЗ
              </label>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
