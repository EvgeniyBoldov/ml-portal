import React from 'react';
import { useChatStatusState } from '../contexts/ChatContext';
import styles from './ChatStatus.module.css';

export default function ChatStatus() {
  const { error, isLoading } = useChatStatusState();

  if (!error && !isLoading) return null;

  return (
    <div className={styles.statusBar}>
      {isLoading && (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          Загрузка...
        </div>
      )}
      {error && <div className={styles.error}>⚠️ {error}</div>}
    </div>
  );
}
