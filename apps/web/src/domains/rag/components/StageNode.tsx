import React from 'react';
import { StageKey, StageState, StageStatus } from '../types';
import styles from './StageNode.module.css';

interface StageNodeProps {
  stage: StageKey;
  state: StageState;
  emphasis?: boolean;
  status?: StageStatus;
  onClick?: () => void;
}

const STAGE_LABELS: Record<StageKey, string> = {
  upload: 'Upload',
  extract: 'Extract',
  normalize: 'Normalize',
  chunk: 'Chunk',
  index: 'Index',
  archive: 'Archive',
};

export function StageNode({ stage, state, emphasis, status, onClick }: StageNodeProps) {
  const tooltipId = `stage-tooltip-${stage}`;
  
  const tooltipContent = status ? (
    <div className={styles.tooltip}>
      <div className={styles.tooltipTitle}>{STAGE_LABELS[stage]}</div>
      {status.started_at && (
        <div className={styles.tooltipRow}>
          <span>Started:</span>
          <span>{new Date(status.started_at).toLocaleTimeString()}</span>
        </div>
      )}
      {status.duration_ms && (
        <div className={styles.tooltipRow}>
          <span>Duration:</span>
          <span>{(status.duration_ms / 1000).toFixed(1)}s</span>
        </div>
      )}
      {status.retries && status.retries > 0 && (
        <div className={styles.tooltipRow}>
          <span>Retries:</span>
          <span>{status.retries}</span>
        </div>
      )}
      {status.error && (
        <div className={styles.tooltipError}>{status.error}</div>
      )}
    </div>
  ) : null;

  const symbol = state === 'ok' ? 'OK' : state === 'error' ? '!' : '–';

  return (
    <div className={styles.container}>
      <button
        className={[
          styles.node,
          styles[`state-${state}`],
          emphasis ? styles.emphasis : '',
        ].join(' ')}
        onClick={onClick}
        aria-pressed={emphasis}
        aria-describedby={tooltipId}
        aria-label={`${STAGE_LABELS[stage]} - ${state}`}
      >
        {state === 'running' ? (
          <span className={styles.spinner} />
        ) : (
          <span className={styles.symbol}>{symbol}</span>
        )}
      </button>
      <div className={styles.caption}>{STAGE_LABELS[stage]}</div>
      {tooltipContent && (
        <div id={tooltipId} role="tooltip" className={styles.tooltipWrapper}>
          {tooltipContent}
        </div>
      )}
    </div>
  );
}
