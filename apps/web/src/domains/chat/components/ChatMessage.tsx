import { useState, memo } from 'react';
import MarkdownRenderer from '@/shared/ui/MarkdownRenderer';
import { Icon } from '@/shared/ui/Icon';
import { buildFileDownloadUrl, buildChatAttachmentFileId } from '@/shared/api/files';
import RAGSources, { type RAGSource } from './RAGSources';
import styles from './ChatMessage.module.css';

interface ChatMessageProps {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt?: string;
  isStreaming?: boolean;
  ragSources?: RAGSource[];
  attachments?: Array<{
    id?: string;
    fileId?: string;
    name: string;
    type?: string;
    sizeBytes?: number;
    url?: string;
  }>;
  answerBlocks?: Array<Record<string, unknown>>;
}

function ChatMessageComponent({
  id,
  role,
  content,
  createdAt,
  isStreaming,
  ragSources,
  attachments,
  answerBlocks,
}: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

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
  const typedBlocks = Array.isArray(answerBlocks) ? answerBlocks : [];

  const handleDownload = async (file: {
    id?: string;
    fileId?: string;
    name: string;
    url?: string;
  }) => {
    try {
      if (file.url) {
        window.open(file.url, '_blank', 'noopener,noreferrer');
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
          <span className={styles.role}>{isUser ? 'Вы' : 'Ассистент'}</span>
          {createdAt && <span className={styles.time}>{formatTime(createdAt)}</span>}
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
          ) : typedBlocks.length > 0 ? (
            <div className={styles.structured}>
              {typedBlocks.map((raw, idx) => {
                const type = String(raw.type || '');
                if (type === 'bigstring') {
                  const value = typeof raw.value === 'string' ? raw.value : '';
                  if (!value) return null;
                  return <MarkdownRenderer key={`block-${idx}`} content={value} />;
                }
                if (type === 'code') {
                  const lang = typeof raw.language === 'string' ? raw.language : 'text';
                  const value = typeof raw.value === 'string' ? raw.value : '';
                  if (!value) return null;
                  return <MarkdownRenderer key={`block-${idx}`} content={`\`\`\`${lang}\n${value}\n\`\`\``} />;
                }
                if (type === 'table') {
                  const columns = Array.isArray(raw.columns) ? raw.columns : [];
                  const rows = Array.isArray(raw.rows) ? raw.rows : [];
                  if (!columns.length) return null;
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
                  const url = typeof raw.url === 'string' ? raw.url : '';
                  const name = typeof raw.name === 'string' ? raw.name : 'file';
                  if (!url) return null;
                  return (
                    <a
                      key={`block-${idx}`}
                      className={styles.fileLink}
                      href={url}
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
              })}
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
            <button
              className={styles.actionBtn}
              onClick={handleCopy}
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

export const ChatMessage = memo(ChatMessageComponent);
export default ChatMessage;
