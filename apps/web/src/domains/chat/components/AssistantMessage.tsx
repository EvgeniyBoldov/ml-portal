import { useState } from 'react';
import MarkdownRenderer from '@/shared/ui/MarkdownRenderer';
import { Icon } from '@/shared/ui/Icon';
import RAGSources from './RAGSources';
import { ChatAttachments } from './ChatAttachments';
import { ChatRunStatus } from './ChatRunStatus';
import type { ActiveChatRun, ChatTimelineMessage } from '../types';
import styles from './Message.module.css';

export function AssistantMessage({ message, isStreaming, run }: { message: ChatTimelineMessage; isStreaming: boolean; run?: ActiveChatRun }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };
  const date = new Date(message.createdAt);
  const time = Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

  return (
    <article className={`${styles.message} ${styles.assistant}`} aria-label="Ответ ассистента">
      <div className={styles.avatar}><Icon name="bot" size={20} /></div>
      <div className={styles.content}>
        <div className={styles.header}>
          <span>Ассистент</span>
          <time>{time}</time>
          {run && <span className={styles.statusLabel}>{run.status === 'running' ? 'Выполняется' : run.status === 'waiting_confirmation' ? 'Ожидает подтверждения' : 'Ожидает ответа'}</span>}
        </div>
        {run && <ChatRunStatus run={run} />}
        {message.content && <div className={styles.assistantBody}><MarkdownRenderer content={message.content} /></div>}
        <ChatAttachments attachments={message.meta?.attachments ?? []} variant="artifact" />
        {(message.meta?.ragSources?.length ?? 0) > 0 && <RAGSources sources={message.meta!.ragSources!} />}
        {!isStreaming && message.content && (
          <div className={styles.actions}>
            {message.meta?.runtimeRunId && <span className={styles.runRef}>run {message.meta.runtimeRunId.slice(0, 8)}</span>}
            <button className={styles.copy} type="button" onClick={() => void copy()} aria-label={copied ? 'Скопировано' : 'Копировать сообщение'}>
              <Icon name={copied ? 'check' : 'copy'} size={14} />
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
