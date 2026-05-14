import Badge from '@/shared/ui/Badge';
import styles from './Inspector.module.css';

interface InspectorNoticeProps {
  tone?: 'info' | 'warn' | 'danger' | 'success' | 'neutral';
  title?: string;
  message: string;
  code?: string;
}

export function InspectorNotice({ tone = 'info', title, message, code }: InspectorNoticeProps) {
  return (
    <div className={[styles.notice, styles[`notice-${tone}`]].join(' ')}>
      {title ? <Badge tone={tone}>{title}</Badge> : null}
      <p className={styles.noticeText}>{message}</p>
      {code ? <p className={styles.noticeCode}><code>{code}</code></p> : null}
    </div>
  );
}
