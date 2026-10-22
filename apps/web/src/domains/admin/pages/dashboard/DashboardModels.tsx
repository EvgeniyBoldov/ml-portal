import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import type { DashboardModel } from '@/shared/api/dashboard';
import { Badge, Button, EntityCard, type DataTableColumn } from '@/shared/ui';
import { State } from './DashboardState';
import { assignment, duration, number, timestamp } from './format';
import { DashboardTable } from './DashboardTable';
import styles from './DashboardTables.module.css';

export function DashboardModels({ models }: { models: DashboardModel[] }) {
  const [modelView, setModelView] = useState<'usage' | 'assignments'>('usage');
  const modelColumns: DataTableColumn<DashboardModel>[] = [
    {
      key: 'name',
      label: 'Модель',
      render: row => (
        <div className={styles.identity}>
          {row.id ? (
            <Link to={`/admin/platform/models/${row.id}`}>{row.name}</Link>
          ) : (
            <strong>{row.name}</strong>
          )}
          <span>
            {row.alias} ·{' '}
            {row.type === 'llm_chat'
              ? 'LLM'
              : row.type === 'embedding'
                ? 'Embedding'
                : row.type}
          </span>
        </div>
      ),
    },
    ...(modelView === 'usage'
      ? ([
          {
            key: 'calls',
            label: 'Вызовы',
            align: 'right',
            render: row => (row.type === 'llm_chat' ? number(row.calls) : '—'),
          },
          {
            key: 'tokens',
            label: 'Токены вх. / вых.',
            align: 'right',
            render: row => (
              <div className={styles.identity}>
                <span className={styles.numeric}>
                  {number(row.tokens_in)} / {number(row.tokens_out)}
                </span>
                {row.calls > 0 &&
                  (row.estimated_calls > 0 ||
                    row.metered_calls < row.calls) && (
                    <span>
                      {row.estimated_calls > 0
                        ? `Оценка: ${number(row.estimated_calls)} выз.`
                        : ''}
                      {row.metered_calls < row.calls
                        ? ` · Нет учёта: ${number(row.calls - row.metered_calls)}`
                        : ''}
                    </span>
                  )}
              </div>
            ),
          },
          {
            key: 'errors',
            label: 'Ошибки',
            align: 'right',
            render: row => (row.type === 'llm_chat' ? number(row.errors) : '—'),
          },
          {
            key: 'duration',
            label: 'Среднее время',
            align: 'right',
            render: row => duration(row.avg_duration_ms),
          },
        ] satisfies DataTableColumn<DashboardModel>[])
      : ([
          {
            key: 'assignments',
            label: 'Где используется',
            render: row =>
              row.assignments.length ? (
                <div className={styles.assignments}>
                  {row.assignments.map(item => (
                    <span key={item}>{assignment(item)}</span>
                  ))}
                </div>
              ) : (
                <span className={styles.muted}>Нет назначений</span>
              ),
          },
        ] satisfies DataTableColumn<DashboardModel>[])),
    {
      key: 'health',
      label: 'Состояние',
      render: row => (
        <div className={styles.identity}>
          {row.enabled ? (
            <State value={row.health} />
          ) : (
            <Badge tone="neutral">Выключена</Badge>
          )}
          <span>
            {row.checked_at
              ? `Проверка ${timestamp(row.checked_at)}`
              : 'Нет проверки'}
          </span>
        </div>
      ),
    },
  ];
  return (
    <EntityCard
      title="Модели"
      className={styles['models-card']}
      actions={
        <div
          className={styles.switcher}
          role="group"
          aria-label="Представление моделей"
        >
          <Button
            size="small"
            variant={modelView === 'usage' ? 'primary' : 'outline'}
            aria-pressed={modelView === 'usage'}
            onClick={() => setModelView('usage')}
          >
            Использование
          </Button>
          <Button
            size="small"
            variant={modelView === 'assignments' ? 'primary' : 'outline'}
            aria-pressed={modelView === 'assignments'}
            onClick={() => setModelView('assignments')}
          >
            Назначения
          </Button>
        </div>
      }
    >
      <div className={styles.table}>
        <DashboardTable
          columns={modelColumns}
          data={models}
          keyField="alias"
          emptyText="Модели не настроены"
        />
      </div>
      <p className={styles.note}>
        Учёт вызовов и токенов — для LLM в чате и Shadow API. Для остальных
        типов показаны назначения и доступность.
      </p>
    </EntityCard>
  );
}
