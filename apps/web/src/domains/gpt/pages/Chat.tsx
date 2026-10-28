import React, { useEffect, useMemo, useRef } from 'react';
import styles from './Chat.module.css';
import { useParams } from 'react-router-dom';
import {
  useChatActions,
  useChatMessagesState,
} from '@/domains/chat/contexts/ChatContext';
import { ChatComposer } from '@/domains/chat/components/ChatComposer';
import { ChatContextPanel } from '@/domains/chat/components/ChatContextPanel';
import { UserMessage } from '@/domains/chat/components/UserMessage';
import { AssistantMessage } from '@/domains/chat/components/AssistantMessage';
import { ConfirmationPrompt } from '@/domains/chat/components/ConfirmationPrompt/ConfirmationPrompt';
import { Icon } from '@/shared/ui/Icon';
import { useChatScroll } from '@/domains/chat/hooks/useChatScroll';
import type { ChatTimelineMessage } from '@/domains/chat/types';

const EMPTY_MESSAGES: ChatTimelineMessage[] = [];

export default function Chat() {
  const { chatId } = useParams();
  const state = useChatMessagesState();
  const {
    loadMessages,
    loadOlderMessages,
    loadPausedRun,
    loadActiveRun,
    setCurrentChat,
    clearPendingState,
    sendMessageStream,
    abortStream,
    resumeStream,
    stopRun,
  } = useChatActions();
  const submissionRef = useRef<AbortController | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [streamError, setStreamError] = React.useState<string | null>(null);
  const [clarifyInput, setClarifyInput] = React.useState('');
  const [clarifyBusy, setClarifyBusy] = React.useState(false);

  const current = useMemo(
    () => (chatId ? state.messagesByChat[chatId] : undefined),
    [chatId, state.messagesByChat]
  );
  const messages = current?.items || EMPTY_MESSAGES;
  const { historyRef, contentRef, hasUnread, scrollToBottom } = useChatScroll(
    chatId,
    messages
  );

  useEffect(() => {
    // Pending confirmation/input is run-specific; drop stale state when chat changes.
    clearPendingState();
    setClarifyInput('');
    setCurrentChat(chatId || null);
    if (chatId) {
      void loadPausedRun(chatId);
      void loadActiveRun(chatId);
    }
    setBusy(false);
    setClarifyBusy(false);
    setStreamError(null);
    return () => {
      submissionRef.current?.abort();
      submissionRef.current = null;
      abortStream();
    };
  }, [chatId, clearPendingState, setCurrentChat, loadPausedRun, loadActiveRun, abortStream]);

  const handleSend = async (
    message: string,
    options: { attachments?: File[] }
  ) => {
    if (!chatId) return false;
    const submission = new AbortController();
    submissionRef.current = submission;
    setBusy(true);
    setStreamError(null);

    try {
      scrollToBottom();
      let artifactIds: string[] = [];
      let attachmentMeta: Array<Record<string, unknown>> = [];
      if (options.attachments?.length) {
        const { uploadChatAttachment } = await import('@shared/api/chats');
        if (submission.signal.aborted) return false;
        const uploaded = await Promise.all(
          options.attachments.map(file =>
            uploadChatAttachment(chatId, file, submission.signal)
          )
        );
        artifactIds = uploaded.map(item => item.artifact_id);
        attachmentMeta = uploaded.map(item => ({
          artifact_id: item.artifact_id,
          file_name: item.file_name,
          file_ext: item.file_ext,
          content_type: item.content_type ?? undefined,
          size_bytes: item.size_bytes,
          status: item.status,
        }));
      }

      // A stopped upload must not start a new turn, even if its response won
      // the race with cancellation or the user has navigated to another chat.
      if (submission.signal.aborted) return false;
      await sendMessageStream(
        chatId,
        message,
        () => {},
        (err: string) => {
          const friendlyErr = _friendlyError(err);
          setStreamError(friendlyErr);
        },
        artifactIds,
        attachmentMeta
      );
      // Once the chat request has been handed to the stream client, its
      // failure is shown in the transcript/banner. Do not put the submitted
      // message back into the composer (which can cause accidental resends).
      return true;
    } catch (e: unknown) {
      if (submission.signal.aborted) return false;
      submission.abort();
      console.error(e);
      setStreamError(
        _friendlyError(
          e instanceof Error ? e.message : 'Ошибка при отправке сообщения'
        )
      );
      return false;
    } finally {
      if (submissionRef.current === submission) {
        submissionRef.current = null;
        setBusy(false);
      }
    }
  };

  const handleClarifySubmit = async () => {
    if (!clarifyInput.trim() || clarifyBusy) return;
    const runId = String(state.pausedRunId || '').trim();
    if (!runId) {
      setStreamError(
        'Сессия ожидания уже завершена или устарела. Отправьте сообщение заново.'
      );
      return;
    }
    setClarifyBusy(true);
    setStreamError(null);
    try {
      const userInput = clarifyInput.trim();
      const resumed = await resumeStream(
        runId,
        'input',
        userInput,
        () => {},
        (err: string) => setStreamError(_friendlyError(err))
      );
      if (resumed) {
        setClarifyInput('');
      }
      if (chatId && resumed) {
        await loadMessages(chatId);
      }
    } catch (e: unknown) {
      const rawError = e instanceof Error ? e.message : 'Ошибка отправки';
      setStreamError(_friendlyError(rawError));
    } finally {
      setClarifyBusy(false);
    }
  };

  const handleInteractionCancel = async () => {
    const runId = String(
      state.pausedRunId || pendingConfirmation?.runId || ''
    ).trim();
    if (!runId || clarifyBusy) return;
    setClarifyBusy(true);
    setStreamError(null);
    try {
      const cancelled = await resumeStream(
        runId,
        'cancel',
        '',
        () => {},
        (err: string) => setStreamError(_friendlyError(err))
      );
      if (cancelled) {
        setClarifyInput('');
        if (chatId) await loadMessages(chatId);
      }
    } finally {
      setClarifyBusy(false);
    }
  };

  function _friendlyError(raw: string): string {
    if (!raw) return 'Произошла ошибка';
    if (raw.includes('rbac_agent_invoke_denied'))
      return '🚫 Нет прав на запуск этого агента. Обратитесь к администратору.';
    if (raw.includes('Paused run not found'))
      return 'Сессия ожидания уже завершена или устарела. Отправьте сообщение заново.';
    if (raw.includes('Missing tools') || raw.includes('no instance'))
      return `⚠️ Инструменты недоступны: ${raw
        .replace(/Missing tools:/gi, '')
        .replace(/Agent unavailable:/gi, '')
        .trim()}`;
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
          <h2 className={styles.emptyTitle}>
            Добро пожаловать в ML Portal Chat
          </h2>
          <p className={styles.emptyDescription}>
            Выберите существующий чат слева или создайте новый, чтобы начать
            общение с AI-ассистентом.
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

  const pendingConfirmation = state.pendingConfirmations[0] || null;
  const isWaitingInput = Boolean(state.pendingInput && !pendingConfirmation);
  const activeRun = state.activeRun;

  return (
    <div className={styles.chatContainer}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerInfo}>
          <h2 className={styles.headerTitle}>Чат</h2>
        </div>
        <ChatContextPanel chatId={chatId} />
      </div>

      {/* Messages */}
      <div className={styles.messagesContainer} ref={historyRef}>
        <div ref={contentRef} className={styles.messagesContent}>
          {current?.olderCursor && (
            <button type="button" onClick={() => void loadOlderMessages(chatId)} disabled={current.loading}>
              Загрузить более ранние сообщения
            </button>
          )}
          {messages.length === 0 && !current?.loading && !current?.error ? (
            <div className={styles.noMessages}>
              <Icon name="sparkles" size={32} />
              <p>Начните диалог, отправив сообщение</p>
            </div>
          ) : (
            messages.map(message => (
              <React.Fragment key={message.id}>
                {message.role === 'user' ? (
                  <UserMessage message={message} />
                ) : null}
                {message.role === 'assistant' && (
                  <AssistantMessage
                    message={message}
                    isStreaming={Boolean(
                      state.isStreaming &&
                        activeRun?.assistantMessageId === message.id
                    )}
                    run={
                      activeRun?.assistantMessageId === message.id
                        ? activeRun
                        : undefined
                    }
                  />
                )}
              </React.Fragment>
            ))
          )}

          {current?.loading && <p role="status">Загрузка истории…</p>}
          {current?.error && (
            <div className={styles.errorBanner} role="alert">
              <span>Не удалось загрузить историю: {current.error}</span>
              <button type="button" onClick={() => void loadMessages(chatId)}>
                Повторить
              </button>
            </div>
          )}

          {/* Error message */}
          {streamError && (
            <div className={styles.errorBanner}>
              <Icon name="x" size={16} />
              <span>{streamError}</span>
            </div>
          )}
        </div>
      </div>
      {hasUnread && (
        <button
          type="button"
          className={styles.jumpToLatest}
          onClick={scrollToBottom}
          aria-label="Перейти к новым сообщениям"
        >
          <Icon name="arrow-down" size={14} />
          <span>Новые сообщения</span>
        </button>
      )}

      <div className={styles.composerSlot}>
        {pendingConfirmation ? (
          <ConfirmationPrompt
            item={pendingConfirmation}
            disabled={clarifyBusy}
            onCancel={() => {
              void handleInteractionCancel();
            }}
            onReject={
              state.hasInteraction
                ? async () => {
                    if (clarifyBusy) return;
                    const runId =
                      pendingConfirmation.runId || state.pausedRunId;
                    if (!runId) return;
                    setClarifyBusy(true);
                    setStreamError(null);
                    try {
                      const resumed = await resumeStream(
                        runId,
                        'answer',
                        false,
                        () => {},
                        err => setStreamError(_friendlyError(err))
                      );
                      if (resumed && chatId) await loadMessages(chatId);
                    } finally {
                      setClarifyBusy(false);
                    }
                  }
                : undefined
            }
            onConfirm={async () => {
              if (clarifyBusy) return;
              const runId = String(
                pendingConfirmation.runId || state.pausedRunId || ''
              ).trim();
              if (!runId) {
                setStreamError('Сессия ожидания уже завершена или устарела.');
                return;
              }
              setClarifyBusy(true);
              setStreamError(null);
              try {
                const resumed = await resumeStream(
                  runId,
                  'confirm',
                  '',
                  () => {},
                  (err: string) => setStreamError(_friendlyError(err))
                );
                if (resumed && chatId) await loadMessages(chatId);
              } finally {
                setClarifyBusy(false);
              }
            }}
          />
        ) : isWaitingInput ? (
          <div className={styles.clarifyBox}>
            <div className={styles.clarifyHeader}>
              <Icon name="help-circle" size={16} />
              <h3>
                {state.pendingInput?.question ||
                  state.pendingInput?.reason ||
                  'Уточните, пожалуйста, запрос'}
              </h3>
            </div>
            <div className={styles.clarifyRow}>
              <textarea
                className={styles.clarifyInput}
                placeholder="Введите уточнение для продолжения..."
                value={clarifyInput}
                onChange={e => setClarifyInput(e.target.value)}
                onKeyDown={e => {
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
              <button
                className={styles.confirmBtn}
                onClick={() => {
                  void handleInteractionCancel();
                }}
                disabled={clarifyBusy}
              >
                Отменить
              </button>
            </div>
          </div>
        ) : (
          <ChatComposer
            key={chatId}
            onSend={handleSend}
            disabled={busy && !state.isStreaming}
            isStreaming={state.isStreaming}
            previousMessage={
              [...messages].reverse().find(message => message.role === 'user')
                ?.content
            }
            onStop={() => {
              submissionRef.current?.abort();
              const runId = state.activeRun?.runId;
              if (chatId && runId) {
                void stopRun(chatId, runId).catch(error => {
                  setStreamError(error instanceof Error ? error.message : 'Не удалось остановить выполнение');
                });
              }
            }}
            placeholder="Напишите сообщение..."
          />
        )}
      </div>
    </div>
  );
}
