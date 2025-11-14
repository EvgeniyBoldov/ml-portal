import React from 'react';
import { StageState } from '../types';
import styles from './IndexModelsLane.module.css';

interface IndexModelsLaneProps {
  models: Array<{
    id: string;
    name: string;
    state: StageState;
  }>;
}

export function IndexModelsLane({ models }: IndexModelsLaneProps) {
  return (
    <div className={styles.lane}>
      {models.map((model) => {
        const symbol = model.state === 'ok' ? 'OK' : model.state === 'error' ? '!' : '–';
        return (
          <div key={model.id} className={styles.row} title={`${model.name}: ${model.state}`}>
            <div className={[styles.circle, styles[`state-${model.state}`]].join(' ')}>
              {model.state === 'running' ? (
                <span className={styles.spinner} />)
                : (<span className={styles.symbol}>{symbol}</span>)}
            </div>
            <div className={styles.name}>{model.name}</div>
          </div>
        );
      })}
    </div>
  );
}
