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
  children?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning' | 'info';
  confirmDisabled?: boolean;
  confirmLoading?: boolean;
  hideCancel?: boolean;
  size?: 'md' | 'half' | 'lg' | 'xl';
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  description,
  children,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  confirmDisabled = false,
  confirmLoading = false,
  hideCancel = false,
  size = 'md',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmVariant = variant === 'info' ? 'primary' : variant;

  return (
    <Modal open={open} title={title} onClose={onCancel} size={size}>
      <div className={styles.content}>
        {(message || description) && (
          <div className={styles.message}>
            {typeof (message ?? description) === 'string'
              ? <p>{message ?? description}</p>
              : (message ?? description)}
          </div>
        )}
        {children && <div className={styles.extra}>{children}</div>}
        <div className={styles.actions}>
          {!hideCancel && (
            <Button variant="outline" onClick={onCancel} disabled={confirmLoading}>
              {cancelLabel}
            </Button>
          )}
          <Button variant={confirmVariant} onClick={onConfirm} disabled={confirmDisabled || confirmLoading}>
            {confirmLoading ? 'Выполняется...' : confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
