import { Icon } from '@/shared/ui/Icon';
import { ChatAttachments } from './ChatAttachments';
import type { ChatTimelineMessage } from '../types';
import styles from './Message.module.css';

export function UserMessage({ message }: { message: ChatTimelineMessage }) {
  return (
    <article className={`${styles.message} ${styles.user}`} aria-label="Сообщение пользователя">
      <div className={styles.avatar}><Icon name="user" size={20} /></div>
      <div className={styles.content}>
        <div className={styles.header}><span>Вы</span><time>{formatTime(message.createdAt)}</time></div>
        {message.content && <div className={styles.userBody}>{message.content}</div>}
        <ChatAttachments attachments={message.meta?.attachments ?? []} variant="user" />
      </div>
    </article>
  );
}

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}
