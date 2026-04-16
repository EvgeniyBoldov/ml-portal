import React from 'react';
import Modal from './Modal';
import Button from './Button';

interface FormModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  onSubmit: () => void;
  saving?: boolean;
  submitDisabled?: boolean;
  submitLabel?: string;
  cancelLabel?: string;
  size?: 'md' | 'half' | 'lg' | 'xl';
  children?: React.ReactNode;
}

export default function FormModal({
  open,
  title,
  onClose,
  onSubmit,
  saving = false,
  submitDisabled = false,
  submitLabel = 'Сохранить',
  cancelLabel = 'Отмена',
  size = 'lg',
  children,
}: FormModalProps) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      size={size}
      footer={(
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
          <Button variant="outline" onClick={onClose}>
            {cancelLabel}
          </Button>
          <Button onClick={onSubmit} disabled={saving || submitDisabled}>
            {saving ? 'Сохранение...' : submitLabel}
          </Button>
        </div>
      )}
    >
      {children}
    </Modal>
  );
}
