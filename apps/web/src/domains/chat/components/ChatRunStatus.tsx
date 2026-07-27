import { useState } from 'react';
import { Icon } from '@/shared/ui/Icon';
import type { ActiveChatRun } from '../types';
import styles from './ChatRunStatus.module.css';

export function ChatRunStatus({ run }: { run: ActiveChatRun }) {
  const [expanded, setExpanded] = useState(false);
  const current = run.progress.at(-1);
  const label = run.status === 'waiting_confirmation' ? 'Ожидается подтверждение' : run.status === 'waiting_input' ? 'Ожидается ваш ответ' : current?.description || 'Готовлю ответ';
  return (
    <section className={styles.card} aria-live="polite" aria-label="Статус выполнения ответа">
      <div className={styles.summary}>
        <Icon name={run.status === 'running' ? 'loader' : 'clock'} size={16} />
        <span>{label}</span>
        {run.progress.length > 1 && <button type="button" onClick={() => setExpanded((value) => !value)}>{expanded ? 'Скрыть' : 'Подробности'}</button>}
      </div>
      {expanded && <ol className={styles.history}>{run.progress.map((item) => <li key={item.id}>{item.description}</li>)}</ol>}
    </section>
  );
}
