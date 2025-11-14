import React from 'react';
import Button from '@shared/ui/Button';
import FilePicker from '@shared/ui/FilePicker';
import Input from '@shared/ui/Input';
import Modal from '@shared/ui/Modal';

interface UploaderProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: () => void;
  file: File | null;
  onFileSelected: (file: File | null) => void;
  uploadTags: string[];
  onUploadTagsChange: (tags: string[]) => void;
  isUploading: boolean;
}

export default function Uploader({
  isOpen,
  onClose,
  onUpload,
  file,
  onFileSelected,
  uploadTags,
  onUploadTagsChange,
  isUploading,
}: UploaderProps) {
  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title="Новый документ"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={onUpload} disabled={isUploading || !file}>
            Загрузить
          </Button>
        </>
      }
    >
      <div className="stack">
        <FilePicker
          onFileSelected={onFileSelected}
          accept=".txt,.pdf,.doc,.docx,.md,.rtf,.odt"
          selectedFile={file}
          label="Выбрать файл"
        />
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
