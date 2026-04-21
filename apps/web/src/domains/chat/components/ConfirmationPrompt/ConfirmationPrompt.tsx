import React from 'react';

import styles from './ConfirmationPrompt.module.css';

export interface ChatConfirmationItem {
  operationFingerprint: string;
  toolSlug: string;
  operation: string;
  riskLevel: string;
  argsPreview: string;
  summary: string;
}

interface ConfirmationPromptProps {
  item: ChatConfirmationItem;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmationPrompt({ item, onConfirm, onCancel }: ConfirmationPromptProps) {
  const confirmRef = React.useRef<HTMLButtonElement | null>(null);

  React.useEffect(() => {
    confirmRef.current?.focus();
  }, []);

  React.useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCancel();
      } else if (event.key === 'Enter') {
        event.preventDefault();
        onConfirm();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onCancel, onConfirm]);

  const riskClass =
    item.riskLevel === 'destructive'
      ? styles.riskDanger
      : item.riskLevel === 'write'
        ? styles.riskWrite
        : styles.riskSafe;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.title}>Требуется подтверждение операции</div>
        <span className={`${styles.risk} ${riskClass}`}>{item.riskLevel || 'safe'}</span>
      </div>
      <div className={styles.line}>Tool: {item.toolSlug || 'unknown'}</div>
      <div className={styles.line}>Operation: {item.operation || 'unknown'}</div>
      <div className={styles.line}>{item.summary || 'Операция требует подтверждения.'}</div>
      {item.argsPreview ? <div className={styles.args}>{item.argsPreview}</div> : null}
      <div className={styles.actions}>
        <button type="button" className={styles.btn} onClick={onCancel}>
          Отменить
        </button>
        <button type="button" className={`${styles.btn} ${styles.btnPrimary}`} onClick={onConfirm} ref={confirmRef}>
          Подтвердить
        </button>
      </div>
    </div>
  );
}
