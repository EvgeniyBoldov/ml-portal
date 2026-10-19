import { buildArtifactDownloadUrl } from '@/shared/api/files';
import { Icon } from '@/shared/ui/Icon';
import type { ChatAttachmentRef } from '../types';
import styles from './ChatAttachments.module.css';

interface ChatAttachmentsProps {
  attachments: ChatAttachmentRef[];
  variant: 'user' | 'artifact';
}

export function ChatAttachments({ attachments, variant }: ChatAttachmentsProps) {
  if (!attachments.length) return null;

  return (
    <div className={styles.list} aria-label={variant === 'user' ? 'Прикреплённые файлы' : 'Файлы результата'}>
      {attachments.map((attachment) => (
        <a
          className={styles.attachment}
          key={attachment.artifactId}
          href={attachment.downloadUrl || buildArtifactDownloadUrl(attachment.artifactId)}
          target="_blank"
          rel="noopener noreferrer"
          title={variant === 'user' ? 'Открыть прикреплённый файл' : 'Открыть файл результата'}
        >
          <Icon name={variant === 'artifact' ? 'download' : 'file'} size={14} />
          <span>{attachment.fileName}</span>
        </a>
      ))}
    </div>
  );
}
