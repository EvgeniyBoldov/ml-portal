import { useState } from 'react';
import { Badge } from '@/shared/ui';
import type { RunFinal } from '../aggregator';
import styles from './TraceV2.module.css';

interface Props {
  final: RunFinal;
}

export function RunFinalBlock({ final }: Props) {
  const [collapsed, setCollapsed] = useState(false);

  const blockCls =
    final.status === 'failed'
      ? styles.blockFinalFailed
      : final.status === 'stopped'
        ? styles.blockFinalStopped
        : styles.blockFinalSuccess;

  const statusTone =
    final.status === 'failed' ? 'danger' : final.status === 'stopped' ? 'warn' : 'success';

  const statusLabel =
    final.status === 'failed' ? 'Failed' : final.status === 'stopped' ? 'Stopped' : 'Completed';

  return (
    <div className={`${styles.block} ${blockCls}`}>
      <div className={styles.blockHeader} onClick={() => setCollapsed((v) => !v)} style={{ cursor: 'pointer', userSelect: 'none' }}>
        <span>↗ Output</span>
        <Badge tone={statusTone as 'success' | 'warn' | 'danger'}>{statusLabel}</Badge>
        <span style={{ marginLeft: 'auto', opacity: 0.4, fontSize: '0.7rem' }}>{collapsed ? '▶' : '▼'}</span>
      </div>
      {!collapsed && (
        <div className={styles.blockBody}>
          {final.answer && (
            <div className={styles.finalAnswer} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{final.answer}</div>
          )}
          {!final.answer && final.status === 'completed' && (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              Ответ не записан. Установите уровень логирования <strong>full</strong> или <strong>brief</strong> на агенте.
            </div>
          )}
          {final.error && (
            <div className={styles.finalError}>
              <div className={styles.finalErrorCode}>{final.error.code}</div>
              {final.error.userMessage && (
                <div className={styles.finalErrorMsg}>{final.error.userMessage}</div>
              )}
              {final.error.operatorMessage && final.error.operatorMessage !== final.error.userMessage && (
                <div className={styles.finalErrorMsg} style={{ marginTop: 4, opacity: 0.7 }}>
                  {final.error.operatorMessage}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
