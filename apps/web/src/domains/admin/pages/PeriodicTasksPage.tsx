import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { qk } from '@/shared/api/keys';
import {
  periodicTasksApi,
  type PeriodicTask,
} from '@/shared/api/periodicTasks';
import {
  Badge,
  Button,
  DataTable,
  EntityPageV2,
  Input,
  Tab,
  type DataTableColumn,
} from '@/shared/ui';
import {
  categories,
  formatSchedule,
  formatTimestamp,
  PERIODIC_TASKS_PATH,
  scheduleStatus,
  scheduleStatuses,
} from '../components/periodicTasks/periodicTaskLabels';
import styles from './PeriodicTasksPage.module.css';

function TaskLink({ task }: { task: PeriodicTask }) {
  const [params] = useSearchParams();
  const query = params.get('q');
  const search = query ? `?${new URLSearchParams({ q: query })}` : '';
  return (
    <Link
      to={`${PERIODIC_TASKS_PATH}/${encodeURIComponent(task.slug)}${search}`}
    >
      {task.name}
    </Link>
  );
}

const columns: DataTableColumn<PeriodicTask>[] = [
  {
    key: 'name',
    label: 'Задача',
    width: '48%',
    sortable: true,
    sortValue: row => row.name,
    render: row => (
      <div className={styles.task}>
        <TaskLink task={row} />
        {row.description && <span>{row.description}</span>}
      </div>
    ),
  },
  {
    key: 'schedule',
    label: 'Расписание',
    render: row =>
      row.is_orphaned ? '—' : formatSchedule(row.default_schedule),
  },
  {
    key: 'enabled',
    label: 'Статус расписания',
    sortable: true,
    sortValue: row => scheduleStatus(row).label,
    filter: {
      kind: 'select',
      options: scheduleStatuses.map(({ value, label }) => ({ value, label })),
      getValue: row => scheduleStatus(row).value,
    },
    render: row => {
      const status = scheduleStatus(row);
      return <Badge tone={status.tone}>{status.label}</Badge>;
    },
  },
  {
    key: 'last_run',
    label: 'Последний запуск',
    sortable: true,
    sortValue: row => row.last_run_at ?? '',
    render: row => formatTimestamp(row.last_run_at),
  },
];

function matchesTask(task: PeriodicTask, query: string) {
  const searchable = [
    task.name,
    task.description,
    task.slug,
    categories[task.category],
    task.category,
    scheduleStatus(task).label,
    formatSchedule(task.default_schedule),
  ]
    .join(' ')
    .toLowerCase()
    .replace(/ё/g, 'е');
  return query
    .trim()
    .toLowerCase()
    .replace(/ё/g, 'е')
    .split(/\s+/)
    .every(word => searchable.includes(word));
}

export default function PeriodicTasksPage() {
  const [params, setParams] = useSearchParams();
  const search = params.get('q') ?? '';
  const list = useQuery({
    queryKey: qk.periodicTasks.list(),
    queryFn: () => periodicTasksApi.list(),
    refetchInterval: 5000,
  });

  return (
    <EntityPageV2
      title="Периодические задачи"
      mode="view"
      breadcrumbs={[{ label: 'Периодические задачи' }]}
    >
      <Tab
        title="Задачи"
        layout="full"
        actions={[
          <div className={styles.headerControls} key="task-controls">
            <Input
              className={styles.search}
              type="search"
              aria-label="Поиск периодических задач"
              placeholder="Поиск по задачам…"
              value={search}
              onChange={event => {
                const next = new URLSearchParams(params);
                if (event.target.value) next.set('q', event.target.value);
                else next.delete('q');
                setParams(next, { replace: true });
              }}
            />
            <Button
              variant="outline"
              onClick={() => void list.refetch()}
              loading={list.isFetching}
            >
              Обновить
            </Button>
          </div>,
        ]}
      >
        {list.isError && (
          <p role="alert">Не удалось загрузить задачи. Нажмите «Обновить».</p>
        )}
        {!list.isError && (
          <div className={styles.table}>
            <DataTable
              columns={columns}
              data={list.data?.items ?? []}
              keyField="slug"
              loading={list.isPending}
              searchable
              searchControl="external"
              searchValue={search}
              searchFilter={matchesTask}
              emptyText="Периодические задачи не найдены"
            />
          </div>
        )}
      </Tab>
    </EntityPageV2>
  );
}
