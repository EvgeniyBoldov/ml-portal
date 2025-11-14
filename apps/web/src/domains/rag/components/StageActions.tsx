import React from 'react';
import { StageKey } from '../types';
import styles from './StageActions.module.css';

interface StageActionsProps {
  stage: StageKey;
  state: string;
  models?: Array<{ id: string; name: string; state: string }>;
  onStart?: () => void;
  onRestart?: () => void;
  onStop?: () => void;
  onRetryModel?: (modelId: string) => void;
}

type ActionItem =
  | { key: string; type: 'button'; label: string; onClick: () => void }
  | { key: string; type: 'label'; label: string }
  | { key: string; type: 'divider' };

export function StageActions({
  stage,
  state,
  models,
  onStart,
  onRestart,
  onStop,
  onRetryModel,
}: StageActionsProps) {
  const canStart = state === 'idle' || state === 'error';
  const canRestart = state === 'ok' || state === 'error';
  const canStop = state === 'running' || state === 'queued';

  const items: ActionItem[] = [];

  if (canStart && onStart) {
    items.push({ key: 'start', type: 'button', label: '▶ Запустить', onClick: onStart });
  }

  if (canRestart && onRestart) {
    items.push({ key: 'restart', type: 'button', label: '🔄 Перезапустить', onClick: onRestart });
  }

  if (canStop && onStop) {
    items.push({ key: 'stop', type: 'button', label: '⏹ Остановить', onClick: onStop });
  }

  if (stage === 'index' && models && models.length > 0 && onRetryModel) {
    const retryable = models.filter((model) => model.state === 'error' || model.state === 'ok');
    if (retryable.length > 0) {
      items.push({ key: 'divider-models', type: 'divider' });
      items.push({ key: 'label-models', type: 'label', label: 'Модели' });
      retryable.forEach((model) => {
        items.push({
          key: `model-${model.id}`,
          type: 'button',
          label: `🔄 ${model.name}`,
          onClick: () => onRetryModel(model.id),
        });
      });
    }
  }

  return (
    <div className={styles.wrapper} role="group" aria-label="Действия этапа">
      {items.length > 0 ? (
        <div className={styles.list}>
          {items.map((item) => {
            if (item.type === 'divider') {
              return <div key={item.key} className={styles.divider} aria-hidden="true" />;
            }
            if (item.type === 'label') {
              return (
                <div key={item.key} className={styles.label}>
                  {item.label}
                </div>
              );
            }
            return (
              <button
                key={item.key}
                type="button"
                className={styles.button}
                onClick={item.onClick}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      ) : (
        <div className={styles.empty}>Нет доступных действий</div>
      )}
    </div>
  );
}
