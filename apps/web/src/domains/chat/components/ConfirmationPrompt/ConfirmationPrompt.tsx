import React from 'react';

import styles from './ConfirmationPrompt.module.css';

export interface ChatConfirmationItem {
  operationFingerprint: string;
  toolSlug: string;
  operation: string;
  riskLevel: string;
  argsPreview: string;
  question: string;
  summary: string;
}

interface ConfirmationPromptProps {
  item: ChatConfirmationItem;
  onConfirm: () => void;
  onCancel: () => void;
  disabled?: boolean;
}

export function ConfirmationPrompt({
  item,
  onConfirm,
  onCancel,
  disabled = false,
}: ConfirmationPromptProps) {
  const confirmRef = React.useRef<HTMLButtonElement | null>(null);

  React.useEffect(() => {
    confirmRef.current?.focus();
  }, []);

  React.useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (!disabled) onCancel();
      } else if (event.key === 'Enter') {
        event.preventDefault();
        if (!disabled) onConfirm();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [disabled, onCancel, onConfirm]);

  const riskClass =
    item.riskLevel === 'destructive'
      ? styles.riskDanger
      : item.riskLevel === 'write'
        ? styles.riskWrite
        : styles.riskSafe;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.title}>
          {item.question || 'Подтвердите действие'}
        </div>
        <span className={`${styles.risk} ${riskClass}`}>
          {item.riskLevel || 'safe'}
        </span>
      </div>
      {item.toolSlug ? (
        <div className={styles.line}>Tool: {item.toolSlug}</div>
      ) : null}
      {item.operation ? (
        <div className={styles.line}>Operation: {item.operation}</div>
      ) : null}
      {item.summary && item.summary !== item.question ? (
        <div className={styles.line}>{item.summary}</div>
      ) : null}
      {item.argsPreview ? (
        <div className={styles.args}>{item.argsPreview}</div>
      ) : null}
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.btn}
          onClick={onCancel}
          disabled={disabled}
        >
          Отменить
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={onConfirm}
          ref={confirmRef}
          disabled={disabled}
        >
          {disabled ? 'Отправка...' : 'Подтвердить'}
        </button>
      </div>
    </div>
  );
}
