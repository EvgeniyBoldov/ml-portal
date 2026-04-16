/**
 * ConfirmDialog - Centralized confirmation dialog
 * Used for destructive actions across the app
 */
import React from 'react';
import Modal from './Modal';
import Button from './Button';
import styles from './ConfirmDialog.module.css';

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message?: React.ReactNode;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning' | 'info';
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmVariant = variant === 'info' ? 'primary' : variant;

  return (
    <Modal open={open} title={title} onClose={onCancel} size="md">
      <div className={styles.content}>
        {(message || description) && (
          <div className={styles.message}>
            {typeof (message ?? description) === 'string'
              ? <p>{message ?? description}</p>
              : (message ?? description)}
          </div>
        )}
        <div className={styles.actions}>
          <Button variant="outline" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant={confirmVariant} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
