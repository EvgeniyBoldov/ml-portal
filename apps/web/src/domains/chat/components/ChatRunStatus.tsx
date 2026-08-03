import { useState } from 'react';
import { Icon } from '@/shared/ui/Icon';
import type { ActiveChatRun } from '../types';
import styles from './ChatRunStatus.module.css';

export function getRecentDistinctProgress(run: ActiveChatRun, limit = 2) {
  const recent = run.progress
    .slice()
    .reverse()
    .filter((item, index, items) => items.findIndex((candidate) => candidate.description === item.description) === index)
    .slice(0, limit)
    .reverse();
  return recent;
}

function getStatusLabel(status: ActiveChatRun['status']) {
  if (status === 'waiting_confirmation') return 'Ожидается подтверждение';
  if (status === 'waiting_input') return 'Ожидается ваш ответ';
  return 'Выполняется';
}

export function ChatRunStatus({ run }: { run: ActiveChatRun }) {
  const [expanded, setExpanded] = useState(false);
  const recent = getRecentDistinctProgress(run);
  const history = run.progress.slice(-10);

  return (
    <section className={styles.card} aria-live="polite" aria-label="Ход выполнения ответа">
      <button
        className={styles.summary}
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-label={expanded ? 'Свернуть ход выполнения' : 'Развернуть ход выполнения'}
      >
        <Icon name={run.status === 'running' ? 'loader' : 'clock'} size={16} />
        <span className={styles.status}>{getStatusLabel(run.status)}</span>
        <span className={styles.toggle}>{expanded ? 'Свернуть' : 'Подробнее'}</span>
      </button>

      {!expanded && (
        <ol className={styles.stages} aria-label="Последние этапы">
          {recent.length > 0 ? recent.map((item, index) => (
            <li key={item.id} className={index === recent.length - 1 ? styles.currentStage : undefined}>
              <span>{index === recent.length - 1 ? 'Сейчас' : 'Перед этим'}</span>
              <strong>{item.description}</strong>
            </li>
          )) : <li className={styles.currentStage}><span>Сейчас</span><strong>Готовлю ответ</strong></li>}
        </ol>
      )}

      {expanded && (
        <ol className={styles.history} aria-label="История выполнения">
          {history.length > 0 ? history.map((item) => (
            <li key={item.id}>
              <span>{item.phase || 'Выполнение'}</span>
              <strong>{item.description}</strong>
            </li>
          )) : <li><strong>Готовлю ответ</strong></li>}
        </ol>
      )}
    </section>
  );
}
