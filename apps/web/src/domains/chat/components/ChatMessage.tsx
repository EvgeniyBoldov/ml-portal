import { useMemo, useState, memo } from 'react';
import MarkdownRenderer from '@/shared/ui/MarkdownRenderer';
import { Icon } from '@/shared/ui/Icon';
import { buildFileDownloadUrl, buildChatAttachmentFileId } from '@/shared/api/files';
import RAGSources, { type RAGSource } from './RAGSources';
import styles from './ChatMessage.module.css';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  createdAt?: string;
  isStreaming?: boolean;
  runtimeStages?: string[];
  meta?: Record<string, unknown>;
}

function ChatMessageComponent({
  role,
  content,
  createdAt,
  isStreaming,
  runtimeStages,
  meta,
}: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const ragSources = useMemo(
    () => (Array.isArray(meta?.rag_sources) ? (meta.rag_sources as RAGSource[]) : undefined),
    [meta?.rag_sources]
  );
  const attachments = useMemo(
    () =>
      Array.isArray(meta?.attachments)
        ? (meta.attachments as Array<Record<string, unknown>>)
            .map((entry) => ({
              id: typeof entry.id === 'string' ? entry.id : undefined,
              fileId: typeof entry.file_id === 'string' ? entry.file_id : undefined,
              downloadUrl:
                typeof entry.download_url === 'string'
                  ? entry.download_url
                  : (typeof entry.url === 'string' ? entry.url : undefined),
              name: typeof entry.file_name === 'string' ? entry.file_name : '',
              type: typeof entry.content_type === 'string' ? entry.content_type : undefined,
              sizeBytes: typeof entry.size_bytes === 'number' ? entry.size_bytes : undefined,
            }))
            .filter((item) => item.name)
        : undefined,
    [meta?.attachments]
  );
  const typedBlocks = useMemo(
    () =>
      Array.isArray(meta?.answer_blocks)
        ? (meta.answer_blocks.filter((item) => item && typeof item === 'object') as Array<Record<string, unknown>>)
        : [],
    [meta?.answer_blocks]
  );
  const runtimeRunId = useMemo(
    () => (typeof meta?.runtime_run_id === 'string' ? meta.runtime_run_id : ''),
    [meta?.runtime_run_id]
  );

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const formatTime = (dateStr?: string) => {
    if (!dateStr) return '';
    try {
      // Handle both ISO strings and timestamps
      const date = typeof dateStr === 'number' ? new Date(dateStr) : new Date(dateStr);
      if (isNaN(date.getTime())) return '';
      return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const isUser = role === 'user';
  const handleDownload = async (file: {
    id?: string;
    fileId?: string;
    downloadUrl?: string;
    name: string;
  }) => {
    try {
      if (file.downloadUrl) {
        window.open(file.downloadUrl, '_blank', 'noopener,noreferrer');
        return;
      }
      const fileId = file.fileId || (file.id ? buildChatAttachmentFileId(file.id) : null);
      if (!fileId) return;
      setDownloadingId(file.id || fileId);
      window.open(buildFileDownloadUrl(fileId), '_blank', 'noopener,noreferrer');
    } catch (err) {
      console.error('Failed to download attachment:', err);
    } finally {
      setDownloadingId(null);
    }
  };

  let renderedStructuredCount = 0;
  const structuredContent = typedBlocks.map((raw, idx) => {
    const type = String(raw.type || '');
    if (type === 'bigstring') {
      const value = typeof raw.value === 'string' ? raw.value : '';
      if (!value) return null;
      renderedStructuredCount += 1;
      return <MarkdownRenderer key={`block-${idx}`} content={value} />;
    }
    if (type === 'code') {
      const lang = typeof raw.language === 'string' ? raw.language : 'text';
      const value = typeof raw.value === 'string' ? raw.value : '';
      if (!value) return null;
      renderedStructuredCount += 1;
      return <MarkdownRenderer key={`block-${idx}`} content={`\`\`\`${lang}\n${value}\n\`\`\``} enableLineBreaks={false} />;
    }
    if (type === 'table') {
      const columns = Array.isArray(raw.columns) ? raw.columns : [];
      const rows = Array.isArray(raw.rows) ? raw.rows : [];
      if (!columns.length) return null;
      renderedStructuredCount += 1;
      return (
        <div className={styles.tableWrap} key={`block-${idx}`}>
          <table className={styles.table}>
            <thead>
              <tr>
                {columns.map((col, cidx) => (
                  <th key={`c-${idx}-${cidx}`}>{String(col)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ridx) => {
                const entry = row as Record<string, unknown>;
                return (
                  <tr key={`r-${idx}-${ridx}`}>
                    {columns.map((col, cidx) => (
                      <td key={`v-${idx}-${ridx}-${cidx}`}>{String(entry[String(col)] ?? '')}</td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      );
    }
    if (type === 'file') {
      const fileId = typeof raw.file_id === 'string' ? raw.file_id : '';
      const downloadUrl =
        typeof raw.download_url === 'string'
          ? raw.download_url
          : (typeof raw.url === 'string' ? raw.url : '');
      const name = typeof raw.name === 'string' ? raw.name : 'file';
      const href = downloadUrl || (fileId ? buildFileDownloadUrl(fileId) : '');
      if (!href) return null;
      renderedStructuredCount += 1;
      return (
        <a
          key={`block-${idx}`}
          className={styles.fileLink}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
        >
          {name}
        </a>
      );
    }
    if (type === 'citations') {
      const items = Array.isArray(raw.items) ? raw.items : [];
      if (!items.length) return null;
      renderedStructuredCount += 1;
      return (
        <div className={styles.citations} key={`block-${idx}`}>
          {items.map((item, sidx) => {
            const source = item as Record<string, unknown>;
            const title = typeof source.title === 'string' ? source.title : `source-${sidx + 1}`;
            const uri = typeof source.uri === 'string' ? source.uri : '';
            return (
              <div key={`src-${idx}-${sidx}`} className={styles.citationItem}>
                {uri ? (
                  <a href={uri} target="_blank" rel="noopener noreferrer">{title}</a>
                ) : (
                  <span>{title}</span>
                )}
              </div>
            );
          })}
        </div>
      );
    }
    return null;
  });

  const hasStructuredOutput = renderedStructuredCount > 0;

  return (
    <div className={`${styles.message} ${isUser ? styles.user : styles.assistant}`}>
      {/* Avatar */}
      <div className={styles.avatar}>
        {isUser ? (
          <Icon name="user" size={20} />
        ) : (
          <Icon name="bot" size={20} />
        )}
      </div>

      {/* Content */}
      <div className={styles.content}>
        <div className={styles.header}>
          <div className={styles.headerMain}>
            <span className={styles.role}>{isUser ? 'Вы' : 'Ассистент'}</span>
            {createdAt && <span className={styles.time}>{formatTime(createdAt)}</span>}
          </div>
          {!isUser && isStreaming && runtimeStages && runtimeStages.length > 0 && (
            <div className={styles.runtimeStages} aria-live="polite">
              {runtimeStages.map((line, idx) => (
                <div key={`${idx}:${line}`} className={styles.runtimeStageLine}>
                  {line}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Attachments */}
        {attachments && attachments.length > 0 && (
          <div className={styles.attachments}>
            {attachments.map((file, idx) => (
              <button
                key={file.id || `${file.name}-${idx}`}
                className={styles.attachment}
                type="button"
                onClick={() => handleDownload(file)}
                disabled={!!downloadingId && downloadingId === (file.id || file.fileId)}
                title="Скачать файл"
              >
                <Icon name="file" size={14} />
                <span>{file.name}</span>
              </button>
            ))}
          </div>
        )}

        {/* Message body */}
        <div className={styles.body}>
          {isUser ? (
            <div className={styles.userText}>{content}</div>
          ) : hasStructuredOutput ? (
            <div className={styles.structured}>
              {structuredContent}
            </div>
          ) : content ? (
            <MarkdownRenderer content={content} />
          ) : isStreaming ? (
            <div className={styles.typing}>
              <span></span>
              <span></span>
              <span></span>
            </div>
          ) : null}
        </div>

        {/* RAG Sources */}
        {ragSources && ragSources.length > 0 && (
          <RAGSources sources={ragSources} />
        )}

        {/* Actions */}
        {!isUser && content && !isStreaming && (
          <div className={styles.actions}>
            {runtimeRunId ? (
              <span className={styles.runtimeRunRef} title={`Run ID: ${runtimeRunId}`}>
                run {runtimeRunId.slice(0, 8)}
              </span>
            ) : null}
            <button
              className={styles.actionBtn}
              onClick={handleCopy}
              type="button"
              aria-label={copied ? 'Скопировано' : 'Копировать сообщение'}
              title={copied ? 'Скопировано!' : 'Копировать'}
            >
              <Icon name={copied ? 'check' : 'copy'} size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function areChatMessagePropsEqual(prev: ChatMessageProps, next: ChatMessageProps) {
  return (
    prev.role === next.role
    && prev.content === next.content
    && prev.createdAt === next.createdAt
    && prev.isStreaming === next.isStreaming
    && prev.runtimeStages === next.runtimeStages
    && prev.meta === next.meta
  );
}

export const ChatMessage = memo(ChatMessageComponent, areChatMessagePropsEqual);
export default ChatMessage;
