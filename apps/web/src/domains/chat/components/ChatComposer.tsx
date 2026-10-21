import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { Icon } from '@/shared/ui/Icon';
import styles from './ChatComposer.module.css';

interface Attachment {
  id: string;
  file: File;
  preview?: string;
}

interface ChatComposerProps {
  onSend: (
    message: string,
    options: { attachments?: File[] }
  ) => void | boolean | Promise<void | boolean>;
  onStop?: () => void;
  isStreaming?: boolean;
  disabled?: boolean;
  placeholder?: string;
  previousMessage?: string;
}

export function ChatComposer({
  onSend,
  onStop,
  isStreaming,
  disabled,
  placeholder,
  previousMessage,
}: ChatComposerProps) {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [showMenu, setShowMenu] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [uploadPolicy, setUploadPolicy] = useState<{
    max_bytes: number;
    allowed_extensions: string[];
    allowed_content_types_by_extension?: Record<string, string[]>;
  } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const attachmentsRef = useRef<Attachment[]>([]);

  const revokePreviews = useCallback((items: Attachment[]) => {
    for (const item of items) {
      if (item.preview) URL.revokeObjectURL(item.preview);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    import('@/shared/api/chats')
      .then(({ getChatUploadPolicy }) => getChatUploadPolicy())
      .then(policy => {
        if (mounted) setUploadPolicy(policy);
      })
      .catch(() => {
        if (mounted) setUploadPolicy(null);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (!menuRef.current) return;
      if (!menuRef.current.contains(event.target as globalThis.Node)) {
        setShowMenu(false);
      }
    };
    if (showMenu) {
      document.addEventListener('mousedown', onClickOutside);
    }
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [showMenu]);

  const handleSubmit = useCallback(async () => {
    if (
      (!text.trim() && attachments.length === 0) ||
      disabled ||
      isStreaming ||
      isSending
    )
      return;

    const submittedText = text;
    const toSend = [...attachments];
    setIsSending(true);
    setText('');
    setAttachments([]);
    setUploadError(null);
    setShowMenu(false);
    try {
      const sent = await onSend(submittedText.trim(), {
        attachments: toSend.map(a => a.file),
      });

      if (sent === false) {
        setText(submittedText);
        setAttachments(toSend);
        return;
      }
      revokePreviews(toSend);
      textareaRef.current?.focus();
    } catch (error) {
      setText(submittedText);
      setAttachments(toSend);
      throw error;
    } finally {
      setIsSending(false);
    }
  }, [
    text,
    attachments,
    disabled,
    isStreaming,
    isSending,
    onSend,
    revokePreviews,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      e.key === 'ArrowUp' &&
      !e.shiftKey &&
      !e.altKey &&
      !e.ctrlKey &&
      !e.metaKey &&
      !text &&
      previousMessage &&
      !disabled &&
      !isStreaming &&
      !isSending
    ) {
      e.preventDefault();
      setText(previousMessage);
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    const maxBytes = uploadPolicy?.max_bytes ?? 50 * 1024 * 1024;
    const allowedExtensions = new Set(
      (
        uploadPolicy?.allowed_extensions ?? [
          'txt',
          'md',
          'pdf',
          'doc',
          'docx',
          'xls',
          'xlsx',
          'csv',
        ]
      ).map(item => item.toLowerCase().replace(/^\./, ''))
    );

    const validFiles: File[] = [];
    let validationError: string | null = null;
    const allowedMimeByExt =
      uploadPolicy?.allowed_content_types_by_extension ?? {};
    for (const file of files) {
      const fileName = (file.name || '').toLowerCase();
      const dotIdx = fileName.lastIndexOf('.');
      const ext = dotIdx >= 0 ? fileName.slice(dotIdx + 1) : '';
      if (!ext || !allowedExtensions.has(ext)) {
        validationError = `Файл "${file.name}" не поддерживается`;
        continue;
      }
      if (file.size > maxBytes) {
        validationError = `Файл "${file.name}" превышает лимит ${(maxBytes / 1024 / 1024).toFixed(0)} МБ`;
        continue;
      }
      const allowedMime = allowedMimeByExt[ext];
      const mime = (file.type || '').toLowerCase();
      if (
        mime &&
        !['application/octet-stream', 'binary/octet-stream'].includes(mime) &&
        Array.isArray(allowedMime) &&
        allowedMime.length > 0 &&
        !allowedMime.includes(mime)
      ) {
        validationError = `Файл "${file.name}" имеет неподдерживаемый MIME: ${mime}`;
        continue;
      }
      validFiles.push(file);
    }

    setUploadError(validationError);
    if (!validFiles.length) {
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    const newAttachments: Attachment[] = validFiles.map(file => ({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file,
      preview: file.type.startsWith('image/')
        ? URL.createObjectURL(file)
        : undefined,
    }));
    setAttachments(prev => [...prev, ...newAttachments]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeAttachment = (id: string) => {
    setAttachments(prev => {
      const att = prev.find(a => a.id === id);
      if (att?.preview) URL.revokeObjectURL(att.preview);
      return prev.filter(a => a.id !== id);
    });
  };

  useEffect(() => {
    attachmentsRef.current = attachments;
  }, [attachments]);

  useEffect(() => {
    return () => {
      revokePreviews(attachmentsRef.current);
    };
  }, [revokePreviews]);

  const locked = disabled || isStreaming || isSending;
  const canStop = (isStreaming || isSending) && !!onStop;
  const canSend = (text.trim().length > 0 || attachments.length > 0) && !locked;
  const acceptValue = useMemo(() => {
    const list = uploadPolicy?.allowed_extensions ?? [
      'txt',
      'md',
      'pdf',
      'doc',
      'docx',
      'xls',
      'xlsx',
      'csv',
    ];
    return list.map(ext => (ext.startsWith('.') ? ext : `.${ext}`)).join(',');
  }, [uploadPolicy]);

  return (
    <div className={styles.composer}>
      {/* Attachments preview */}
      {attachments.length > 0 && (
        <div className={styles.attachments}>
          {attachments.map(att => (
            <div key={att.id} className={styles.attachment}>
              {att.preview ? (
                <img
                  src={att.preview}
                  alt={att.file.name}
                  className={styles.attachmentPreview}
                />
              ) : (
                <div className={styles.attachmentIcon}>
                  <Icon name="file" size={14} />
                </div>
              )}
              <span className={styles.attachmentName}>{att.file.name}</span>
              <button
                className={styles.attachmentRemove}
                aria-label={`Удалить вложение ${att.file.name}`}
                onClick={() => removeAttachment(att.id)}
                type="button"
                disabled={locked}
              >
                <Icon name="x" size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Main input area */}
      <div className={styles.inputArea}>
        {/* Textarea */}
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || 'Напишите сообщение...'}
          aria-label="Сообщение"
          disabled={locked}
          rows={1}
        />

        {/* Actions */}
        <div className={styles.actions}>
          <div className={styles.plusMenu} ref={menuRef}>
            <button
              className={styles.actionButton}
              onClick={() => setShowMenu(v => !v)}
              type="button"
              title="Добавить"
              aria-label="Открыть меню вложений"
              disabled={locked}
            >
              <Icon name="plus" size={20} />
            </button>
            {showMenu && (
              <div className={styles.menuDropdown}>
                <button
                  className={styles.menuItem}
                  type="button"
                  onClick={() => {
                    setShowMenu(false);
                    fileInputRef.current?.click();
                  }}
                >
                  <Icon name="paperclip" size={16} />
                  <span>Загрузить файл</span>
                </button>
              </div>
            )}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileSelect}
            className={styles.fileInput}
            accept={acceptValue}
            disabled={locked}
          />

          {canStop ? (
            <button
              className={`${styles.sendButton} ${styles.active}`}
              onClick={onStop}
              type="button"
              title="Остановить генерацию"
              aria-label="Остановить генерацию"
            >
              <Icon name="square" size={16} />
            </button>
          ) : (
            <button
              className={`${styles.sendButton} ${canSend ? styles.active : ''}`}
              onClick={handleSubmit}
              disabled={!canSend}
              type="button"
              title="Отправить (Enter)"
              aria-label="Отправить сообщение"
            >
              <Icon name="send" size={20} />
            </button>
          )}
        </div>
      </div>
      {uploadError && <div className={styles.uploadError}>{uploadError}</div>}
    </div>
  );
}

export default ChatComposer;
