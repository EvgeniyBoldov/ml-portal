import { buildArtifactDownloadUrl } from '@/shared/api/files';
import { Icon } from '@/shared/ui/Icon';
import type { ChatAttachmentRef } from '../types';
import styles from './ChatAttachments.module.css';

interface ChatAttachmentsProps {
  attachments: ChatAttachmentRef[];
  variant: 'user' | 'artifact';
}

function fileExtension(fileName: string): string {
  const dot = fileName.lastIndexOf('.');
  return dot > 0 ? fileName.slice(dot + 1).toLowerCase() : '';
}

function fileKind(fileName: string): string {
  const extension = fileExtension(fileName);
  if (/^(doc|docx|odt|rtf)$/.test(extension)) return 'word';
  if (/^(xls|xlsx|ods|csv)$/.test(extension)) return 'sheet';
  if (/^(ppt|pptx|odp)$/.test(extension)) return 'slides';
  if (extension === 'pdf') return 'pdf';
  if (/^(png|jpe?g|gif|webp|svg|bmp|tiff?)$/.test(extension)) return 'image';
  if (/^(txt|md|log|json|xml|ya?ml)$/.test(extension)) return 'text';
  return 'default';
}

function formatSize(sizeBytes?: number): string | null {
  if (sizeBytes === undefined || !Number.isFinite(sizeBytes) || sizeBytes < 0) {
    return null;
  }
  if (sizeBytes < 1024) return `${sizeBytes} Б`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} КБ`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} МБ`;
}

export function ChatAttachments({
  attachments,
  variant,
}: ChatAttachmentsProps) {
  if (!attachments.length) return null;

  return (
    <div
      className={styles.list}
      aria-label={
        variant === 'user' ? 'Прикреплённые файлы' : 'Файлы результата'
      }
    >
      {attachments.map(attachment => (
        <AttachmentCard key={attachment.artifactId} attachment={attachment} />
      ))}
    </div>
  );
}

function AttachmentCard({ attachment }: { attachment: ChatAttachmentRef }) {
  const size = formatSize(attachment.sizeBytes);
  const extension = fileExtension(attachment.fileName)
    .slice(0, 4)
    .toUpperCase();

  return (
    <a
      className={`${styles.attachment} ${styles[fileKind(attachment.fileName)]}`}
      href={
        attachment.downloadUrl ||
        buildArtifactDownloadUrl(attachment.artifactId)
      }
      target="_blank"
      rel="noopener noreferrer"
      title={attachment.fileName}
    >
      <span className={styles.fileIcon} aria-hidden="true">
        <Icon name="file-text" size={19} />
        {extension && <span>{extension}</span>}
      </span>
      <span className={styles.fileInfo}>
        <span className={styles.fileName}>{attachment.fileName}</span>
        {size && <span className={styles.fileSize}>{size}</span>}
      </span>
      {attachment.sourceLabel && (
        <span
          className={`${styles.sourceLabel} ${styles[`source${attachment.sourceLabel}`]}`}
        >
          {attachment.sourceLabel}
        </span>
      )}
    </a>
  );
}
