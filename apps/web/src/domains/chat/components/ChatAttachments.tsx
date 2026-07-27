import { useState } from 'react';
import { buildFileDownloadUrl } from '@/shared/api/files';
import { Icon } from '@/shared/ui/Icon';
import type { ChatAttachmentRef } from '../types';
import styles from './ChatAttachments.module.css';

interface ChatAttachmentsProps {
  attachments: ChatAttachmentRef[];
  variant: 'user' | 'artifact';
}

export function ChatAttachments({ attachments, variant }: ChatAttachmentsProps) {
  const [openingId, setOpeningId] = useState<string | null>(null);
  if (!attachments.length) return null;

  const openAttachment = (attachment: ChatAttachmentRef) => {
    setOpeningId(attachment.id);
    window.open(buildFileDownloadUrl(attachment.fileId), '_blank', 'noopener,noreferrer');
    setOpeningId(null);
  };

  return (
    <div className={styles.list} aria-label={variant === 'user' ? 'Прикреплённые файлы' : 'Файлы результата'}>
      {attachments.map((attachment) => (
        <button
          className={styles.attachment}
          key={attachment.id}
          type="button"
          onClick={() => openAttachment(attachment)}
          disabled={openingId === attachment.id}
          title={variant === 'user' ? 'Открыть прикреплённый файл' : 'Открыть файл результата'}
        >
          <Icon name={variant === 'artifact' ? 'download' : 'file'} size={14} />
          <span>{attachment.fileName}</span>
        </button>
      ))}
    </div>
  );
}
