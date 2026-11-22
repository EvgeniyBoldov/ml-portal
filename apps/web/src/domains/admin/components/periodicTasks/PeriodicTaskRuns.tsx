import { useId } from 'react';
import type {
  PeriodicRunDetail,
  PeriodicRunSummary,
  PeriodicTask,
} from '@/shared/api/periodicTasks';
import { Badge, Block, Button, Select } from '@/shared/ui';
import {
  formatDuration,
  formatTimestamp,
  runStatus,
} from './periodicTaskLabels';
import {
  eventCleanupSummary,
  isActivePeriodicRun,
  runSourceLabel,
} from './periodicRunPresentation';
import { PeriodicRunResult } from './PeriodicRunResult';
import styles from './PeriodicTaskRuns.module.css';

function RunSummary({
  task,
  run,
}: {
  task: PeriodicTask;
  run: PeriodicRunDetail;
}) {
  const outcome = eventCleanupSummary(task.slug, run);
  const status = runStatus(run.status);
  const when = run.started_at || run.created_at;
  const dateLabel = run.started_at
    ? 'Начало'
    : run.status === 'queued'
      ? 'В очереди с'
      : 'Создан';

  return (
    <div className={styles.summary} aria-live="polite">
      {outcome && <strong className={styles.outcome}>{outcome.label}</strong>}
      <div className={styles.metadata}>
        <Badge tone={status.tone}>{status.label}</Badge>
        <span>{runSourceLabel(run.source)}</span>
        <span>
          {dateLabel} <time dateTime={when}>{formatTimestamp(when)}</time>
        </span>
        {run.duration_ms !== null && (
          <span>Длительность {formatDuration(run.duration_ms)}</span>
        )}
      </div>
      {outcome?.retention && (
        <p className={styles.muted}>{outcome.retention}</p>
      )}
      {run.error && <pre className={styles.error}>{run.error}</pre>}
      {run.result != null && (
        <PeriodicRunResult
          value={run.result}
          scalarLabel={outcome ? 'Удалено событий' : undefined}
        />
      )}
      {run.result_limited && (
        <p className={styles.muted}>
          Результат превышает лимит хранения или не поддерживает отображение.
        </p>
      )}
      {run.result == null && !run.result_limited && !run.error && (
        <p className={styles.muted}>
          {isActivePeriodicRun(run.status)
            ? 'Результат появится после завершения.'
            : 'У этого запуска нет данных результата.'}
        </p>
      )}
    </div>
  );
}

function RunJournal({ run }: { run: PeriodicRunDetail }) {
  return (
    <Block title="Журнал выполнения" icon="file">
      {run.events.length ? (
        <ol className={styles.events}>
          {run.events.map((event, index) => (
            <li key={`${event.at}-${index}`}>
              <time dateTime={event.at} title={formatTimestamp(event.at)}>
                {new Date(event.at).toLocaleTimeString('ru-RU')}
              </time>
              <Badge
                tone={
                  event.level === 'ERROR' || event.level === 'CRITICAL'
                    ? 'danger'
                    : event.level === 'WARNING'
                      ? 'warn'
                      : 'neutral'
                }
              >
                {event.level}
              </Badge>
              <span>{event.message}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className={styles.muted}>
          {isActivePeriodicRun(run.status)
            ? 'Записи воркера появятся после завершения попытки.'
            : 'У этого запуска нет записей журнала.'}
        </p>
      )}
    </Block>
  );
}

interface Props {
  task: PeriodicTask;
  runs: PeriodicRunSummary[];
  selectedId: string;
  run?: PeriodicRunDetail;
  runPending: boolean;
  runError: boolean;
  missingRun: boolean;
  onSelect: (id: string) => void;
  onRetry: () => void;
}

export function PeriodicTaskRuns({
  task,
  runs,
  selectedId,
  run,
  runPending,
  runError,
  missingRun,
  onSelect,
  onRetry,
}: Props) {
  const selectorId = useId();
  const options = runs.map(item => ({
    value: item.id,
    label: `${formatTimestamp(item.created_at)} · ${runSourceLabel(item.source)} · ${runStatus(item.status).label}`,
  }));
  if (selectedId && !options.some(option => option.value === selectedId)) {
    options.unshift({
      value: selectedId,
      label: missingRun ? 'Запуск недоступен' : 'Загрузка выбранного запуска…',
    });
  }
  const lastStatus = runStatus(task.last_status);

  return (
    <div className={styles.sections}>
      <Block title="Результат запуска" icon="activity">
        {options.length > 0 && (
          <div className={styles.selector}>
            <label htmlFor={selectorId}>Последние запуски</label>
            <Select
              id={selectorId}
              options={options}
              value={selectedId}
              onChange={onSelect}
            />
          </div>
        )}
        {missingRun ? (
          <div role="status" className={styles.state}>
            <p>Этот запуск больше недоступен в истории задачи.</p>
            {runs.length > 0 && (
              <Button variant="outline" onClick={() => onSelect('')}>
                Открыть последний запуск
              </Button>
            )}
          </div>
        ) : runError ? (
          <div role="alert" className={styles.state}>
            <p>Не удалось загрузить запуск.</p>
            <Button variant="outline" onClick={onRetry}>
              Повторить
            </Button>
          </div>
        ) : run ? (
          <RunSummary key={run.id} task={task} run={run} />
        ) : selectedId && runPending ? (
          <p className={styles.muted} role="status">
            Загружаем журнал и результат…
          </p>
        ) : (
          <div className={styles.summary}>
            {task.last_run_at && (
              <div className={styles.metadata}>
                <Badge tone={lastStatus.tone}>{lastStatus.label}</Badge>
                <span>{formatTimestamp(task.last_run_at)}</span>
                {task.last_duration_ms != null && (
                  <span>{formatDuration(task.last_duration_ms)}</span>
                )}
              </div>
            )}
            {task.last_error && (
              <pre className={styles.error}>{task.last_error}</pre>
            )}
            <p className={styles.muted}>
              {task.last_run_at
                ? 'Журнал и результат появятся после нового запуска.'
                : 'У этой задачи пока нет запусков.'}
            </p>
          </div>
        )}
      </Block>
      {run && <RunJournal run={run} />}
    </div>
  );
}
