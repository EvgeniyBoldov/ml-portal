import React from 'react';
import { StageKey, StageState, StageStatus } from '../types';
import styles from './StagesGraph.module.css';
import { StageColumn } from './StageColumn';

interface StagesGraphProps {
  stages: StageStatus[];
  embedModels?: Array<{ id: string; name: string; state: StageState }>;
  indexModels?: Array<{ id: string; name: string; state: StageState }>;
  selected?: StageKey;
  selectedModelId?: string;
  onSelect: (stage: StageKey, modelId?: string) => void;
}

export function StagesGraph({ stages, embedModels, indexModels, selected, selectedModelId, onSelect }: StagesGraphProps) {
  const visible = stages.filter((s) => s.stage !== 'archive' || s.state === 'ok');

  return (
    <div className={styles.graph}>
      <div className={styles.grid} style={{ gridTemplateColumns: `repeat(${visible.length}, 1fr)` }}>
        {visible.map((s) => (
          <StageColumn
            key={s.stage}
            stage={s.stage}
            state={s.state as StageState}
            models={s.stage === 'embedding' ? embedModels : s.stage === 'index' ? indexModels : undefined}
            isActive={selected === s.stage}
            activeModelId={(s.stage === 'embedding' || s.stage === 'index') ? selectedModelId : undefined}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}
