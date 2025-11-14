import React from 'react';
import { StageKey, StageState } from '../types';
import styles from './StageColumn.module.css';

const STAGE_LABELS: Record<StageKey, string> = {
  upload: 'Upload',
  extract: 'Extract',
  normalize: 'Normalize',
  chunk: 'Chunk',
  embedding: 'Embedding',
  index: 'Index',
  archive: 'Archive',
};

interface StageColumnProps {
  stage: StageKey;
  state: StageState;
  models?: Array<{ id: string; name: string; state: StageState }>;
  isActive?: boolean;
  activeModelId?: string;
  onSelect?: (stage: StageKey, modelId?: string) => void;
}

export function StageColumn({ stage, state, models, isActive = false, activeModelId, onSelect }: StageColumnProps) {
  const columnClassName = [styles.column, isActive ? styles.active : ''].filter(Boolean).join(' ');

  const handleSelect = (modelId?: string) => onSelect?.(stage, modelId);
  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleSelect();
    }
  };

  const normalizeState = (v: string): StageState => {
    switch (v.toLowerCase()) {
      case 'completed':
      case 'success':
        return 'ok';
      case 'pending':
        return 'queued';
      case 'failed':
      case 'fail':
        return 'error';
      case 'in_progress':
        return 'running';
      default:
        return (v as StageState) || 'idle';
    }
  };

  const renderCircle = (s: StageState | string, key?: string, name?: string, modelId?: string) => {
    const st = normalizeState(String(s));
    const symbol = st === 'ok' ? 'OK' : st === 'error' ? '!' : st === 'queued' || st === 'idle' ? '–' : '';
    const isActiveCircle = isActive && (modelId ? activeModelId === modelId : true);
    const circleClassName = [styles.circle, styles[`state-${st}`], isActiveCircle ? styles.activeCircle : '']
      .filter(Boolean)
      .join(' ');

    return (
      <div
        key={key || st}
        className={circleClassName}
        role="button"
        tabIndex={0}
        onClick={() => handleSelect(modelId)}
        onKeyDown={handleKeyDown}
        aria-pressed={isActiveCircle}
        aria-label={`${STAGE_LABELS[stage]}${name ? ` — ${name}` : ''}: ${st}`}
      >
        {st === 'running' ? (
          <span className={styles.spinner} aria-hidden="true" />
        ) : (
          <span className={styles.symbol}>{symbol}</span>
        )}
      </div>
    );
  };

  const renderTimeline = () => {
    if ((stage === 'index' || stage === 'embedding') && models && models.length > 0) {
      return models.map((m, idx) => (
        <React.Fragment key={m.id}>
          {renderCircle(m.state, m.id, m.name, m.id)}
          {idx < models.length - 1 && <div className={styles.arrow} aria-hidden="true" />}
          <div className={styles.modelName}>{m.name}</div>
        </React.Fragment>
      ));
    }

    return (
      <>
        {renderCircle(state)}
      </>
    );
  };

  return (
    <div className={columnClassName}>
      <div className={styles.header}>{STAGE_LABELS[stage]}</div>
      <div className={styles.body}>
        {renderTimeline()}
      </div>
    </div>
  );
}
