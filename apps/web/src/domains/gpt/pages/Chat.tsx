import React, { useEffect, useMemo, useRef } from 'react';
import styles from './Chat.module.css';
import { useNavigate, useParams } from 'react-router-dom';
import { useChat } from '@/domains/chat/contexts/ChatContext';
import EmptyState from '@shared/ui/EmptyState';
import Button from '@shared/ui/Button';
import { ChatMessage } from '@/domains/chat/components/ChatMessage';
import { ChatComposer } from '@/domains/chat/components/ChatComposer';
import { Icon } from '@/shared/ui/Icon';
import type { RAGSource } from '@/domains/chat/components/RAGSources';

function asRagSources(value: unknown): RAGSource[] | undefined {
  return Array.isArray(value) ? (value as RAGSource[]) : undefined;
}

function asAttachments(
  value: unknown
): Array<{ id?: string; fileId?: string; name: string; type?: string; sizeBytes?: number; url?: string }> | undefined {
  if (!Array.isArray(value)) return undefined;
  const items: Array<{ id?: string; fileId?: string; name: string; type?: string; sizeBytes?: number; url?: string }> = [];
  for (const raw of value) {
    if (!raw || typeof raw !== 'object') continue;
    const entry = raw as Record<string, unknown>;
    const name = typeof entry.file_name === 'string' ? entry.file_name : '';
    if (!name) continue;
    items.push({
      id: typeof entry.id === 'string' ? entry.id : undefined,
      fileId: typeof entry.file_id === 'string' ? entry.file_id : undefined,
      name,
      type: typeof entry.content_type === 'string' ? entry.content_type : undefined,
      sizeBytes: typeof entry.size_bytes === 'number' ? entry.size_bytes : undefined,
      url: typeof entry.url === 'string' ? entry.url : undefined,
    });
  }
  return items.length ? items : undefined;
}

function asAnswerBlocks(value: unknown): Array<Record<string, unknown>> | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.filter((item) => item && typeof item === 'object') as Array<Record<string, unknown>>;
}

export default function Chat() {
  const { chatId } = useParams();
  const nav = useNavigate();
  const { state, loadMessages, setCurrentChat, clearPendingState, sendMessageStream } = useChat();
  const historyRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = React.useState(false);
  const [streamError, setStreamError] = React.useState<string | null>(null);
  const [clarifyInput, setClarifyInput] = React.useState('');
  const [clarifyBusy, setClarifyBusy] = React.useState(false);

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
    // Pending confirmation/input is run-specific; drop stale state when chat changes.
    clearPendingState();
    setClarifyInput('');
    setCurrentChat(chatId);
    if (!state.messagesByChat[chatId]?.loaded) {
      loadMessages(chatId).catch(console.error);
    }
    setBusy(false);
    setStreamError(null);
  }, [chatId]);

  // Normalize content
  const normalizeContent = (content: unknown): string => {
    if (typeof content === 'string') return content;
    if (content && typeof content === 'object') {
      const text = (content as { text?: unknown }).text;
      if (typeof text === 'string') return text;
    }
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

    try {
      let attachmentIds: string[] = [];
      let attachmentMeta: Array<Record<string, unknown>> = [];
      if (options.attachments?.length) {
        const { uploadChatAttachment } = await import('@shared/api/chats');
        const uploaded = await Promise.all(
          options.attachments.map((file) => uploadChatAttachment(chatId, file))
        );
        attachmentIds = uploaded.map((item) => item.id);
        attachmentMeta = uploaded.map((item) => ({
          id: item.id,
          file_id: item.file_id,
          file_name: item.file_name,
          file_ext: item.file_ext,
          content_type: item.content_type ?? undefined,
          size_bytes: item.size_bytes,
          status: item.status,
        }));
      }

      await sendMessageStream(
        chatId,
        message,
        false,
        () => {},
        (err: string) => {
          const friendlyErr = _friendlyError(err);
          setStreamError(friendlyErr);
        },
        options.agentSlug,
        attachmentIds,
        attachmentMeta
      );
    } catch (e: unknown) {
      console.error(e);
      setStreamError(_friendlyError(e instanceof Error ? e.message : 'Ошибка при отправке сообщения'));
    } finally {
      setBusy(false);
    }
  };

  const handleClarifySubmit = async () => {
    if (!clarifyInput.trim() || clarifyBusy) return;
    setClarifyBusy(true);
    setStreamError(null);
    try {
      if (state.pausedRunId) {
        const { resumeRun } = await import('@shared/api/chats');
        await resumeRun(state.pausedRunId, 'input', clarifyInput.trim());
        setClarifyInput('');
        if (chatId) {
          await loadMessages(chatId);
        }
        clearPendingState();
      } else {
        // Triage clarify path has no resumable run_id; continue as a normal user message.
        const message = clarifyInput.trim();
        clearPendingState();
        setClarifyInput('');
        await handleSend(message, {});
      }
    } catch (e: unknown) {
      const rawError = e instanceof Error ? e.message : 'Ошибка отправки уточнения';
      if (rawError.includes('Paused run not found')) {
        // Stale run_id: fallback to normal message flow.
        const message = clarifyInput.trim();
        clearPendingState();
        setClarifyInput('');
        if (chatId) {
          await loadMessages(chatId);
        }
        if (message) {
          await handleSend(message, {});
          return;
        }
      }
      setStreamError(_friendlyError(rawError));
    } finally {
      setClarifyBusy(false);
    }
  };

  function _friendlyError(raw: string): string {
    if (!raw) return 'Произошла ошибка';
    if (raw.includes('Paused run not found'))
      return 'Сессия ожидания уже завершена или устарела. Отправьте сообщение заново.';
    if (raw.includes('Missing tools') || raw.includes('no instance'))
      return `⚠️ Инструменты недоступны: ${raw.replace(/Missing tools:/gi, '').replace(/Agent unavailable:/gi, '').trim()}`;
    if (raw.includes('Missing credentials'))
      return `🔑 Нет доступа к инструменту: требуются учётные данные`;
    if (raw.includes('unavailable'))
      return `⚠️ Агент временно недоступен. Обратитесь к администратору.`;
    if (raw.includes('Access denied') || raw.includes('denied'))
      return `🚫 Доступ запрещён. Обратитесь к администратору.`;
    return raw;
  }

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

  const isWaitingInput = Boolean(state.pendingInput && !state.pendingConfirmation);
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
              ragSources={asRagSources(m.meta?.rag_sources)}
              attachments={asAttachments(m.meta?.attachments)}
              answerBlocks={asAnswerBlocks(m.meta?.answer_blocks)}
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

      {/* Confirmation required banner */}
      {state.pendingConfirmation && (
        <div className={styles.confirmationBanner}>
          <div className={styles.confirmationText}>
            <Icon name="alert-triangle" size={16} />
            <span>{state.pendingConfirmation.reason}</span>
          </div>
          <div className={styles.confirmationActions}>
            <button
              className={`${styles.confirmBtn} ${styles.confirmBtnCancel}`}
              onClick={async () => {
                if (state.pausedRunId) {
                  try {
                    const { resumeRun } = await import('@shared/api/chats');
                    await resumeRun(state.pausedRunId, 'cancel');
                    clearPendingState();
                  } catch (e) {
                    console.error('Failed to cancel run', e);
                  }
                }
                setStreamError(null);
                setBusy(false);
              }}
            >
              Отменить
            </button>
            <button
              className={`${styles.confirmBtn} ${styles.confirmBtnApprove}`}
              onClick={async () => {
                if (state.pausedRunId) {
                  try {
                    const { resumeRun } = await import('@shared/api/chats');
                    await resumeRun(state.pausedRunId, 'confirm');
                    if (chatId) {
                      await loadMessages(chatId);
                    }
                    clearPendingState();
                  } catch (e) {
                    console.error('Failed to confirm run', e);
                  }
                }
                setStreamError(null);
                setBusy(false);
              }}
            >
              Подтвердить
            </button>
          </div>
        </div>
      )}

      {/* Waiting for user input block */}
      {isWaitingInput && (
        <div className={styles.clarifyBox}>
          <div className={styles.waitingInputText}>
            <Icon name="help-circle" size={16} />
            <span>{state.pendingInput?.question || state.pendingInput?.reason || 'Агент ожидает вашего ответа'}</span>
          </div>
          <div className={styles.clarifyRow}>
            <textarea
              className={styles.clarifyInput}
              placeholder="Введите уточнение для продолжения..."
              value={clarifyInput}
              onChange={(e) => setClarifyInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void handleClarifySubmit();
                }
              }}
              rows={2}
              disabled={clarifyBusy}
            />
            <button
              className={`${styles.confirmBtn} ${styles.confirmBtnApprove}`}
              onClick={handleClarifySubmit}
              disabled={!clarifyInput.trim() || clarifyBusy}
            >
              {clarifyBusy ? 'Отправка...' : 'Ответить'}
            </button>
          </div>
        </div>
      )}

      {/* Composer */}
      {!isWaitingInput && (
        <ChatComposer
          onSend={handleSend}
          disabled={busy}
          placeholder="Напишите сообщение..."
        />
      )}
    </div>
  );
}
