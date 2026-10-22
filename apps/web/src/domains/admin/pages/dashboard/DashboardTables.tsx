import React from 'react';
import { Link } from 'react-router-dom';
import type {
  DashboardOverview,
  DashboardAgent,
  DashboardCollection,
  DashboardMemoryScope,
} from '@/shared/api/dashboard';
import { Badge, EntityCard, type DataTableColumn } from '@/shared/ui';
import { bytes, duration, number, timestamp } from './format';
import { State, Progress } from './DashboardState';
import { DashboardModels } from './DashboardModels';
import { DashboardTable } from './DashboardTable';
import styles from './DashboardTables.module.css';

export function DashboardTables({ data }: { data: DashboardOverview }) {
  const agentColumns: DataTableColumn<DashboardAgent>[] = [
    {
      key: 'name',
      label: 'Агент',
      render: row => (
        <div className={styles.identity}>
          {row.id ? (
            <Link to={`/admin/agents/${row.id}`}>{row.name}</Link>
          ) : (
            <strong>{row.name}</strong>
          )}
          <span>{row.origin === 'shadow' ? 'Shadow API' : 'Чат'}</span>
        </div>
      ),
    },
    {
      key: 'executions',
      label: 'Запуски',
      align: 'right',
      render: row => number(row.executions),
    },
    {
      key: 'users',
      label: 'Пользователи',
      align: 'right',
      render: row => number(row.users),
    },
    {
      key: 'errors',
      label: 'Ошибки',
      align: 'right',
      render: row => number(row.errors),
    },
    {
      key: 'duration',
      label: 'Среднее время',
      align: 'right',
      render: row => duration(row.avg_duration_ms),
    },
  ];
  const collectionColumns: DataTableColumn<DashboardCollection>[] = [
    {
      key: 'name',
      label: 'Коллекция',
      render: row => (
        <div className={styles.identity}>
          <Link to={`/admin/collections/${encodeURIComponent(row.slug)}`}>
            {row.name}
          </Link>
          <span>
            {row.embedding_models.join(', ') || 'Нет embedding-индексов'}
          </span>
        </div>
      ),
    },
    {
      key: 'documents',
      label: 'Документы',
      align: 'right',
      render: row => number(row.documents),
    },
    {
      key: 'source_bytes',
      label: 'Исходники',
      align: 'right',
      render: row => (
        <div className={styles.identity}>
          <span className={styles.numeric}>{bytes(row.source_bytes)}</span>
          {row.unknown_sizes > 0 && (
            <span>Неизвестен размер: {number(row.unknown_sizes)}</span>
          )}
        </div>
      ),
    },
    {
      key: 'chunks',
      label: 'Чанки',
      align: 'right',
      render: row => number(row.chunks),
    },
    {
      key: 'progress',
      label: 'Готово / в работе / частично / ошибки',
      render: row => (
        <Progress
          ready={row.ready}
          processing={row.processing}
          failed={row.failed}
          partial={row.partial}
        />
      ),
    },
  ];
  const memoryColumns: DataTableColumn<DashboardMemoryScope>[] = [
    {
      key: 'name',
      label: 'Проект памяти',
      render: row => (
        <div className={styles.identity}>
          <Link to="/admin/memory">{row.name}</Link>
          <span>{row.key}</span>
        </div>
      ),
    },
    {
      key: 'status',
      label: 'Индекс',
      render: row => (
        <div className={styles.identity}>
          <State value={row.status} />
          {row.indexed_at && <span>{timestamp(row.indexed_at)}</span>}
        </div>
      ),
    },
    {
      key: 'documents',
      label: 'Документы',
      align: 'right',
      render: row => number(row.documents),
    },
    {
      key: 'nodes',
      label: 'Узлы / связи',
      align: 'right',
      render: row => `${number(row.nodes)} / ${number(row.edges)}`,
    },
    {
      key: 'pending',
      label: 'В работе / ошибки',
      render: row => <Progress processing={row.pending} failed={row.failed} />,
    },
  ];

  return (
    <div className={styles.sections}>
      <DashboardModels models={data.models} />
      <EntityCard
        title="Используемые агенты"
        actions={<Link to="/admin/agent-runs">Журнал запусков →</Link>}
      >
        <div className={styles.table}>
          <DashboardTable
            columns={agentColumns}
            data={data.agents.map(row => ({
              ...row,
              key: `${row.slug}:${row.origin}`,
            }))}
            keyField="key"
            emptyText="За выбранный период агенты не запускались"
          />
        </div>
        <p className={styles.note}>
          Запуски включают повторные попытки выполнения задачи.
        </p>
      </EntityCard>
      <EntityCard
        title="RAG по коллекциям"
        actions={<Badge tone="neutral">Сейчас</Badge>}
      >
        <div className={styles.table}>
          <DashboardTable
            columns={collectionColumns}
            data={data.collections}
            keyField="id"
            emptyText="Документных коллекций нет"
          />
        </div>
        <p className={styles.note}>
          Объём исходных файлов, без индексов и кешей. Один документ может
          входить в несколько коллекций.
        </p>
      </EntityCard>
      <EntityCard
        title="HippoRAG · проекты памяти"
        actions={<Badge tone="neutral">Сейчас</Badge>}
      >
        {!data.memory_available && (
          <p className={styles.note} role="status">
            Worker недоступен. Готовность графов неизвестна.
          </p>
        )}
        <div className={styles.table}>
          <DashboardTable
            columns={memoryColumns}
            data={data.memory_scopes}
            keyField="key"
            emptyText="Проекты памяти не настроены"
          />
        </div>
        <p className={styles.note}>
          Размер активного графа каждого проекта. Знак «—» означает, что размер
          ещё не измерен.
        </p>
      </EntityCard>
    </div>
  );
}
