import { useState } from 'react';
import { Icon } from '@/shared/ui/Icon';
import type { ActiveChatRun, ChatRuntimeProgress } from '../types';
import styles from './ChatRunStatus.module.css';

export function getRecentDistinctProgress(run: ActiveChatRun, limit = 2) {
  const recent = run.progress
    .slice()
    .reverse()
    .filter(
      (item, index, items) =>
        items.findIndex(
          candidate => candidate.description === item.description
        ) === index
    )
    .slice(0, limit)
    .reverse();
  return recent;
}

function getStatusLabel(status: ActiveChatRun['status']) {
  if (status === 'waiting_confirmation') return 'Ожидается подтверждение';
  if (status === 'waiting_input') return 'Ожидается ваш ответ';
  return 'Выполняется';
}

function ProgressOutcome({ outcome }: Pick<ChatRuntimeProgress, 'outcome'>) {
  // An older stage is not necessarily successful. Use only explicit outcomes.
  if (outcome === 'completed') {
    return (
      <span className={styles.success} role="img" aria-label="Завершено">
        <Icon name="check" size={14} />
      </span>
    );
  }
  if (outcome === 'failed' || outcome === 'error') {
    return (
      <span className={styles.failure} role="img" aria-label="Ошибка">
        <Icon name="x" size={14} />
      </span>
    );
  }
  return null;
}

export function ChatRunStatus({ run }: { run: ActiveChatRun }) {
  const [expanded, setExpanded] = useState(false);
  const recent = getRecentDistinctProgress(run);
  const history = run.progress.slice(-10);

  return (
    <section
      className={styles.card}
      aria-live="polite"
      aria-label="Ход выполнения ответа"
    >
      <button
        className={styles.summary}
        type="button"
        onClick={() => setExpanded(value => !value)}
        aria-expanded={expanded}
        aria-label={
          expanded ? 'Свернуть ход выполнения' : 'Развернуть ход выполнения'
        }
      >
        <Icon name={run.status === 'running' ? 'loader' : 'clock'} size={16} />
        <span className={styles.status}>{getStatusLabel(run.status)}</span>
        <span className={styles.toggle}>
          {expanded ? 'Свернуть' : 'Подробнее'}
        </span>
      </button>

      {!expanded && (
        <ol className={styles.stages} aria-label="Последние этапы">
          {recent.length > 0 ? (
            recent.map((item, index) => (
              <li
                key={item.id}
                className={
                  index === recent.length - 1
                    ? styles['current-stage']
                    : styles['previous-stage']
                }
              >
                <strong>{item.description}</strong>
                <ProgressOutcome outcome={item.outcome} />
              </li>
            ))
          ) : (
            <li className={styles['current-stage']}>
              <strong>Готовлю ответ</strong>
            </li>
          )}
        </ol>
      )}

      {expanded && (
        <ol className={styles.history} aria-label="История выполнения">
          {history.length > 0 ? (
            history.map(item => (
              <li key={item.id}>
                <strong>{item.description}</strong>
                <ProgressOutcome outcome={item.outcome} />
              </li>
            ))
          ) : (
            <li>
              <strong>Готовлю ответ</strong>
            </li>
          )}
        </ol>
      )}
    </section>
  );
}
