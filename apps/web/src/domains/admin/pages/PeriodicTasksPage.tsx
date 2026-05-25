import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { periodicTasksApi, qk, type PeriodicTask } from '@/shared/api';
import { EntityPageV2, Tab, Badge, Button, DataTable, type DataTableColumn } from '@/shared/ui';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

function formatSchedule(schedule: Record<string, unknown>): string {
  const type = String(schedule.type || 'unknown');
  if (type === 'interval') return `every ${String(schedule.seconds || '?')}s`;
  if (type === 'crontab') {
    return `${String(schedule.minute ?? '*')} ${String(schedule.hour ?? '*')} ${String(schedule.day_of_month ?? '*')} ${String(schedule.month_of_year ?? '*')} ${String(schedule.day_of_week ?? '*')}`;
  }
  return JSON.stringify(schedule);
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString('ru-RU');
}

function statusTone(status?: string | null): 'neutral' | 'success' | 'warn' | 'danger' | 'info' {
  if (!status) return 'neutral';
  if (status === 'success') return 'success';
  if (status === 'running' || status === 'queued') return 'info';
  if (status === 'failure') return 'danger';
  if (status === 'skipped') return 'warn';
  return 'neutral';
}

const STATUS_OPTIONS = [
  { value: '', label: 'Все' },
  { value: 'success', label: 'success' },
  { value: 'running', label: 'running' },
  { value: 'queued', label: 'queued' },
  { value: 'failure', label: 'failure' },
  { value: 'skipped', label: 'skipped' },
];

export default function PeriodicTasksPage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: qk.periodicTasks.list(),
    queryFn: () => periodicTasksApi.list(),
    refetchInterval: 5000,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ slug, enabled }: { slug: string; enabled: boolean }) => periodicTasksApi.toggle(slug, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.periodicTasks.all() });
      showSuccess('Статус задачи обновлен');
    },
    onError: (e: Error) => showError(e.message || 'Не удалось изменить статус задачи'),
  });

  const runNowMutation = useMutation({
    mutationFn: (slug: string) => periodicTasksApi.runNow(slug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.periodicTasks.all() });
      showSuccess('Задача отправлена в выполнение');
    },
    onError: (e: Error) => showError(e.message || 'Не удалось запустить задачу'),
  });

  const columns: DataTableColumn<PeriodicTask>[] = useMemo(() => [
    {
      key: 'slug',
      label: 'Slug',
      sortable: true,
      filter: { kind: 'text', placeholder: 'Фильтр slug...' },
      sortValue: (row) => row.slug,
      render: (row) => <code>{row.slug}</code>,
    },
    {
      key: 'category',
      label: 'Категория',
      sortable: true,
      filter: { kind: 'text', placeholder: 'Фильтр категории...' },
      sortValue: (row) => row.category,
      render: (row) => <Badge tone="neutral">{row.category}</Badge>,
    },
    {
      key: 'schedule',
      label: 'Расписание',
      sortable: true,
      sortValue: (row) => formatSchedule(row.default_schedule || {}),
      render: (row) => formatSchedule(row.default_schedule || {}),
    },
    {
      key: 'enabled',
      label: 'Статус',
      sortable: true,
      filter: {
        kind: 'select',
        options: [
          { value: '', label: 'Все' },
          { value: 'true', label: 'Включена' },
          { value: 'false', label: 'Выключена' },
        ],
        match: 'equals',
        getValue: (row) => String(Boolean(row.is_enabled)),
      },
      sortValue: (row) => Number(Boolean(row.is_enabled)),
      render: (row) => <Badge tone={row.is_enabled ? 'success' : 'warn'}>{row.is_enabled ? 'Включена' : 'Выключена'}</Badge>,
    },
    {
      key: 'last_run',
      label: 'Последний запуск',
      sortable: true,
      sortValue: (row) => row.last_run_at ?? '',
      render: (row) => formatDate(row.last_run_at),
    },
    {
      key: 'last_status',
      label: 'Результат',
      sortable: true,
      filter: {
        kind: 'select',
        options: STATUS_OPTIONS,
        match: 'equals',
        getValue: (row) => row.last_status ?? '',
      },
      sortValue: (row) => row.last_status ?? '',
      render: (row) => <Badge tone={statusTone(row.last_status)}>{row.last_status || '—'}</Badge>,
    },
    {
      key: 'last_duration_ms',
      label: 'Длительность',
      sortable: true,
      sortValue: (row) => row.last_duration_ms ?? -1,
      render: (row) => row.last_duration_ms != null ? `${row.last_duration_ms}ms` : '—',
    },
    {
      key: 'actions',
      label: 'Действия',
      render: (row) => (
        <div style={{ display: 'flex', gap: 8 }}>
          <Button
            variant="outline"
            onClick={() => runNowMutation.mutate(row.slug)}
            disabled={runNowMutation.isPending || row.is_orphaned}
          >
            Старт
          </Button>
          <Button
            variant={row.is_enabled ? 'danger' : 'success'}
            onClick={() => toggleMutation.mutate({ slug: row.slug, enabled: !row.is_enabled })}
            disabled={toggleMutation.isPending}
          >
            {row.is_enabled ? 'Выключить' : 'Включить'}
          </Button>
        </div>
      ),
    },
  ], [runNowMutation, toggleMutation]);

  return (
    <EntityPageV2 title="Периодические задачи" mode="view" loading={isLoading}>
      <Tab
        title="Список"
        layout="full"
        actions={[
          <Button key="refresh" variant="outline" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? 'Обновление...' : 'Обновить'}
          </Button>,
        ]}
      >
        <DataTable
          columns={columns}
          data={data?.items ?? []}
          keyField="slug"
          searchable
          searchPlaceholder="Поиск по задачам..."
          emptyText="Периодические задачи не найдены"
        />
      </Tab>
    </EntityPageV2>
  );
}
