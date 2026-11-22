import { useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from '@/shared/api/errors';
import { qk } from '@/shared/api/keys';
import {
  periodicTasksApi,
  type PeriodicRunDetail,
} from '@/shared/api/periodicTasks';
import { Button, ConfirmDialog, EntityPageV2, Tab } from '@/shared/ui';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { PeriodicTaskRuns } from '../components/periodicTasks/PeriodicTaskRuns';
import {
  isActivePeriodicRun,
  needsRunConfirmation,
} from '../components/periodicTasks/periodicRunPresentation';
import { PeriodicTaskSettings } from '../components/periodicTasks/PeriodicTaskSettings';
import { PERIODIC_TASKS_PATH } from '../components/periodicTasks/periodicTaskLabels';
import styles from './PeriodicTaskPage.module.css';

const pollingMs = 3000;

function isMissingRun(error: unknown) {
  return error instanceof ApiError && error.status === 404;
}

function PeriodicTaskDetail({ slug }: { slug: string }) {
  const [params, setParams] = useSearchParams();
  const [confirmRun, setConfirmRun] = useState(false);
  const client = useQueryClient();
  const success = useSuccessToast();
  const error = useErrorToast();
  const detail = useQuery({
    queryKey: qk.periodicTasks.detail(slug),
    queryFn: () => periodicTasksApi.get(slug),
    refetchInterval: pollingMs,
  });
  const task = detail.data;
  const selectedId = params.get('run') || task?.runs[0]?.id || '';
  const execution = useQuery({
    queryKey: qk.periodicTasks.run(slug, selectedId),
    queryFn: () => periodicTasksApi.getRun(slug, selectedId),
    enabled: !!task && !!selectedId,
    staleTime: 0,
    retry: (count, failure) => !isMissingRun(failure) && count < 1,
    refetchInterval: query => {
      if (isMissingRun(query.state.error)) return false;
      const state = query.state.data?.status;
      return state && !isActivePeriodicRun(state) ? false : pollingMs;
    },
  });

  function selectRun(id: string) {
    setParams(
      previous => {
        const next = new URLSearchParams(previous);
        if (id) next.set('run', id);
        else next.delete('run');
        return next;
      },
      { replace: true }
    );
  }

  const refresh = () =>
    client.invalidateQueries({ queryKey: qk.periodicTasks.all() });
  const runNow = useMutation({
    mutationFn: () => periodicTasksApi.runNow(slug),
    onSuccess: async result => {
      setConfirmRun(false);
      if (result.task_id) {
        const id = result.task_id;
        client.setQueryData<PeriodicRunDetail>(
          qk.periodicTasks.run(slug, id),
          current =>
            current ?? {
              id,
              source: 'manual',
              status: 'queued',
              created_at: new Date().toISOString(),
              started_at: null,
              finished_at: null,
              duration_ms: null,
              events: [],
              result: null,
              result_limited: false,
              error: null,
            }
        );
        selectRun(id);
      } else {
        success('Запуск поставлен в очередь');
      }
      await refresh();
    },
    onError: (cause: Error) => {
      if (!confirmRun) error(cause.message || 'Не удалось запустить задачу');
    },
  });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => periodicTasksApi.toggle(slug, enabled),
    onSuccess: async ({ is_enabled }) => {
      success(is_enabled ? 'Расписание включено' : 'Расписание выключено');
      await refresh();
    },
    onError: (cause: Error) =>
      error(cause.message || 'Не удалось изменить расписание'),
  });
  const parentQuery = params.get('q');
  const parent = parentQuery
    ? `${PERIODIC_TASKS_PATH}?${new URLSearchParams({ q: parentQuery })}`
    : PERIODIC_TASKS_PATH;
  const missingRun = isMissingRun(execution.error);
  const run = missingRun ? undefined : execution.data;
  const runs = task?.runs ?? [];
  const displayedRuns = run
    ? runs.some(item => item.id === run.id)
      ? runs.map(item => (item.id === run.id ? run : item))
      : [run, ...runs]
    : runs;
  const confirmDeletion = needsRunConfirmation(slug);
  const runButton = confirmDeletion ? 'Запустить очистку' : 'Запустить сейчас';
  const detailError = !task && detail.isError && (
    <p role="alert">
      Не удалось загрузить задачу.{' '}
      <Button variant="ghost" onClick={() => void detail.refetch()}>
        Повторить
      </Button>
    </p>
  );

  return (
    <div className={styles.page}>
      <EntityPageV2
        title={task?.name ?? 'Периодическая задача'}
        mode="view"
        loading={detail.isPending}
        breadcrumbs={[
          { label: 'Периодические задачи', href: parent },
          { label: task?.name ?? 'Задача' },
        ]}
        defaultTab="runs"
        actionButtons={
          task && !task.is_orphaned ? (
            <div className={styles.actions}>
              <Button
                loading={runNow.isPending}
                onClick={() => {
                  runNow.reset();
                  if (confirmDeletion) setConfirmRun(true);
                  else runNow.mutate();
                }}
              >
                {runButton}
              </Button>
              <Button
                variant="outline"
                loading={toggle.isPending}
                onClick={() => toggle.mutate(!task.is_enabled)}
              >
                {task.is_enabled
                  ? 'Выключить расписание'
                  : 'Включить расписание'}
              </Button>
            </div>
          ) : undefined
        }
      >
        <Tab id="runs" title="Запуски" layout="full">
          {detailError}
          {task && (
            <PeriodicTaskRuns
              task={task}
              runs={displayedRuns}
              selectedId={selectedId}
              run={run}
              missingRun={missingRun}
              runPending={execution.isPending}
              runError={execution.isError && !run}
              onSelect={selectRun}
              onRetry={() => void execution.refetch()}
            />
          )}
        </Tab>
        <Tab id="settings" title="Настройки" layout="full">
          {detailError}
          {task && <PeriodicTaskSettings task={task} />}
        </Tab>
      </EntityPageV2>
      {task && confirmDeletion && (
        <ConfirmDialog
          open={confirmRun}
          title="Запустить очистку сейчас?"
          message={task.description ?? task.name}
          confirmLabel="Запустить очистку"
          cancelLabel="Отмена"
          confirmLoading={runNow.isPending}
          onCancel={() => {
            if (!runNow.isPending) setConfirmRun(false);
          }}
          onConfirm={() => runNow.mutate()}
        >
          {runNow.isError && <p role="alert">{runNow.error.message}</p>}
        </ConfirmDialog>
      )}
    </div>
  );
}

export default function PeriodicTaskPage() {
  const { slug = '' } = useParams();
  return <PeriodicTaskDetail key={slug} slug={slug} />;
}
