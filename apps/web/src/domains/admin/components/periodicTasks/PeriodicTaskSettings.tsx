import type { PeriodicTask } from '@/shared/api/periodicTasks';
import { Badge, Block } from '@/shared/ui';
import {
  categories,
  formatSchedule,
  scheduleStatus,
} from './periodicTaskLabels';
import styles from './PeriodicTaskSettings.module.css';

export function PeriodicTaskSettings({ task }: { task: PeriodicTask }) {
  const status = scheduleStatus(task);
  return (
    <div className={styles.settings}>
      <Block title="Расписание" icon="clock">
        {task.description && (
          <p className={styles.description}>{task.description}</p>
        )}
        <dl className={styles.facts}>
          <div>
            <dt>Периодичность</dt>
            <dd>
              {task.is_orphaned ? '—' : formatSchedule(task.default_schedule)}
            </dd>
          </div>
          <div>
            <dt>Статус расписания</dt>
            <dd>
              <Badge tone={status.tone}>{status.label}</Badge>
            </dd>
          </div>
          <div>
            <dt>Категория</dt>
            <dd>{categories[task.category] ?? task.category}</dd>
          </div>
        </dl>
        {!task.is_orphaned && !task.is_enabled && (
          <p className={styles.scheduleNote}>Задачу можно запустить вручную.</p>
        )}
      </Block>
      <Block title="Технические сведения" icon="file-text">
        <dl className={styles.facts}>
          <div>
            <dt>Идентификатор</dt>
            <dd>
              <code>{task.slug}</code>
            </dd>
          </div>
          <div>
            <dt>Задача Celery</dt>
            <dd>
              <code>{task.task_path}</code>
            </dd>
          </div>
        </dl>
      </Block>
    </div>
  );
}
