import React from 'react';
import Button from '@shared/ui/Button';
import FilePicker from '@shared/ui/FilePicker';
import Input from '@shared/ui/Input';
import Modal from '@shared/ui/Modal';

interface UploaderProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: () => void;
  files: File[];
  onFilesSelected: (files: File[]) => void;
  uploadTags: string[];
  onUploadTagsChange: (tags: string[]) => void;
  isUploading: boolean;
}

export default function Uploader({
  isOpen,
  onClose,
  onUpload,
  files,
  onFilesSelected,
  uploadTags,
  onUploadTagsChange,
  isUploading,
}: UploaderProps) {
  const handleRemoveFile = (index: number) => {
    const newFiles = [...files];
    newFiles.splice(index, 1);
    onFilesSelected(newFiles);
  };

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title="Загрузка документов"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={onUpload} disabled={isUploading || files.length === 0}>
            {isUploading ? 'Загрузка...' : `Загрузить (${files.length})`}
          </Button>
        </>
      }
    >
      <div className="stack">
        <FilePicker
          onFilesSelected={(newFiles) => onFilesSelected([...files, ...newFiles])}
          accept=".txt,.pdf,.doc,.docx,.md,.rtf,.odt"
          multiple={true}
          label="Выбрать файлы"
        />
        
        {files.length > 0 && (
          <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {files.map((file, index) => (
              <div 
                key={`${file.name}-${index}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px',
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '14px'
                }}
              >
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '300px' }}>
                  {file.name} <span style={{ color: 'var(--color-muted)', fontSize: '12px' }}>({(file.size / 1024 / 1024).toFixed(2)} MB)</span>
                </span>
                <button 
                  onClick={() => handleRemoveFile(index)}
                  style={{ 
                    background: 'none', 
                    border: 'none', 
                    cursor: 'pointer', 
                    padding: '4px',
                    color: 'var(--color-muted)' 
                  }}
                  type="button"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}

        <div>
          <label>Теги (опционально):</label>
          <Input
            placeholder="Введите теги через запятую..."
            value={uploadTags.join(', ')}
            onChange={e =>
              onUploadTagsChange(
                e.target.value
                  .split(',')
                  .map(t => t.trim())
                  .filter(Boolean)
              )
            }
          />
        </div>
      </div>
    </Modal>
  );
}
