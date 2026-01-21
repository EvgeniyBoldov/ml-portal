import { useState, useRef, useCallback } from 'react';
import { Icon } from '@/shared/ui/Icon';
import { useChatAgents, type ChatAgent } from '@/shared/api/hooks/useChats';
import styles from './ChatComposer.module.css';

interface Attachment {
  id: string;
  file: File;
  preview?: string;
}

interface ChatComposerProps {
  onSend: (message: string, options: { agentSlug?: string; attachments?: File[] }) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatComposer({ onSend, disabled, placeholder }: ChatComposerProps) {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [showAgentPicker, setShowAgentPicker] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: agents = [], isLoading: agentsLoading } = useChatAgents();

  const currentAgent = agents.find(a => a.slug === selectedAgent) || agents[0];

  const handleSubmit = useCallback(() => {
    if (!text.trim() && attachments.length === 0) return;
    if (disabled) return;

    onSend(text.trim(), {
      agentSlug: selectedAgent || currentAgent?.slug,
      attachments: attachments.map(a => a.file),
    });

    setText('');
    setAttachments([]);
    textareaRef.current?.focus();
  }, [text, attachments, selectedAgent, currentAgent, disabled, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const newAttachments: Attachment[] = files.map(file => ({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file,
      preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined,
    }));
    setAttachments(prev => [...prev, ...newAttachments]);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const removeAttachment = (id: string) => {
    setAttachments(prev => {
      const att = prev.find(a => a.id === id);
      if (att?.preview) {
        URL.revokeObjectURL(att.preview);
      }
      return prev.filter(a => a.id !== id);
    });
  };

  const handleAgentSelect = (slug: string) => {
    setSelectedAgent(slug);
    setShowAgentPicker(false);
  };

  const canSend = (text.trim().length > 0 || attachments.length > 0) && !disabled;

  return (
    <div className={styles.composer}>
      {/* Attachments preview */}
      {attachments.length > 0 && (
        <div className={styles.attachments}>
          {attachments.map(att => (
            <div key={att.id} className={styles.attachment}>
              {att.preview ? (
                <img src={att.preview} alt={att.file.name} className={styles.attachmentPreview} />
              ) : (
                <div className={styles.attachmentIcon}>
                  <Icon name="file" size={20} />
                </div>
              )}
              <span className={styles.attachmentName}>{att.file.name}</span>
              <button
                className={styles.attachmentRemove}
                onClick={() => removeAttachment(att.id)}
                type="button"
              >
                <Icon name="x" size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Main input area */}
      <div className={styles.inputArea}>
        {/* Agent selector */}
        <div className={styles.agentSelector}>
          <button
            className={styles.agentButton}
            onClick={() => setShowAgentPicker(!showAgentPicker)}
            type="button"
            title="Выбрать ассистента"
          >
            <Icon name={currentAgent?.has_collections ? 'file-text' : currentAgent?.has_rag ? 'database' : 'sparkles'} size={18} />
            <span className={styles.agentName}>{currentAgent?.name || 'Ассистент'}</span>
            <Icon name="chevron-down" size={14} />
          </button>

          {showAgentPicker && (
            <div className={styles.agentDropdown}>
              {agentsLoading ? (
                <div className={styles.agentOption}>Загрузка...</div>
              ) : (
                agents.map(agent => (
                  <button
                    key={agent.slug}
                    className={`${styles.agentOption} ${agent.slug === (selectedAgent || currentAgent?.slug) ? styles.selected : ''}`}
                    onClick={() => handleAgentSelect(agent.slug)}
                    type="button"
                  >
                    <Icon name={agent.has_collections ? 'file-text' : agent.has_rag ? 'database' : 'sparkles'} size={16} />
                    <div className={styles.agentInfo}>
                      <span className={styles.agentOptionName}>{agent.name}</span>
                      {agent.description && (
                        <span className={styles.agentDescription}>{agent.description}</span>
                      )}
                    </div>
                    {agent.has_rag && (
                      <span className={styles.ragBadge}>RAG</span>
                    )}
                    {agent.has_collections && (
                      <span className={styles.ragBadge}>DATA</span>
                    )}
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || 'Напишите сообщение...'}
          disabled={disabled}
          rows={1}
        />

        {/* Actions */}
        <div className={styles.actions}>
          {/* File upload */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileSelect}
            className={styles.fileInput}
            accept="image/*,.pdf,.doc,.docx,.txt,.md"
          />
          <button
            className={styles.actionButton}
            onClick={() => fileInputRef.current?.click()}
            type="button"
            title="Прикрепить файл"
            disabled={disabled}
          >
            <Icon name="paperclip" size={20} />
          </button>

          {/* Send button */}
          <button
            className={`${styles.sendButton} ${canSend ? styles.active : ''}`}
            onClick={handleSubmit}
            disabled={!canSend}
            type="button"
            title="Отправить (Enter)"
          >
            <Icon name="send" size={20} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatComposer;
