import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getDashboard, type DashboardPeriod } from '@/shared/api/dashboard';
import { qk } from '@/shared/api/keys';
import {
  Alert,
  Badge,
  Button,
  EntityCard,
  EntityPageV2,
  Tab,
} from '@/shared/ui';
import { StatCard } from '../components';
import { DashboardTables } from './dashboard/DashboardTables';
import { UsageChart } from './dashboard/UsageChart';
import { number, timestamp } from './dashboard/format';
import styles from './DashboardPage.module.css';

export function DashboardPage() {
  const [days, setDays] = useState<DashboardPeriod>(7);
  const { data, isPending, isFetching, isError } = useQuery({
    queryKey: qk.admin.dashboard(days),
    queryFn: () => getDashboard(days),
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 1,
    refetchInterval: 60_000,
  });
  const canCompare =
    data &&
    new Date(data.coverage_started_at).getTime() <=
      new Date(data.period_start).getTime() - days * 86_400_000;
  const trend = (current: number, previous: number) =>
    canCompare && previous > 0
      ? {
          value: Math.round((100 * (current - previous)) / previous),
          label: 'к прошлому периоду',
        }
      : undefined;

  return (
    <EntityPageV2
      title="Дашборд"
      mode="view"
      actionButtons={
        <div className={styles.toolbar}>
          <div
            className={styles.periods}
            role="group"
            aria-label="Период статистики"
          >
            {([1, 7, 30] as const).map(period => (
              <Button
                key={period}
                size="small"
                variant={days === period ? 'primary' : 'outline'}
                aria-pressed={days === period}
                onClick={() => setDays(period)}
              >
                {period === 1 ? '1 день' : `${period} дней`}
              </Button>
            ))}
          </div>
        </div>
      }
    >
      <Tab title="Обзор" layout="custom">
        <div className={styles.content} aria-busy={isFetching}>
          {isError && (
            <Alert variant="danger" title="Не удалось обновить дашборд">
              Данные временно недоступны. Попробуйте позже.
            </Alert>
          )}
          {isPending && (
            <div className={styles.empty} role="status">
              Загрузка обзора платформы…
            </div>
          )}
          {data && (
            <>
              <section
                className={styles.stats}
                aria-label="Использование за выбранный период"
              >
                <StatCard
                  title="Запросы"
                  value={number(data.current.requests)}
                  icon="message-square"
                  color="primary"
                  trend={trend(data.current.requests, data.previous.requests)}
                />
                <StatCard
                  title="Активные пользователи"
                  value={number(data.current.active_users)}
                  icon="users"
                  color="info"
                  trend={trend(
                    data.current.active_users,
                    data.previous.active_users
                  )}
                />
                <StatCard
                  title="Задействованные агенты"
                  value={number(data.current.active_agents)}
                  icon="bot"
                  color="success"
                  trend={trend(
                    data.current.active_agents,
                    data.previous.active_agents
                  )}
                />
                <StatCard
                  title="Запросы с ошибкой"
                  value={
                    data.current.error_rate === null
                      ? '—'
                      : `${data.current.error_rate}%`
                  }
                  icon="alert-triangle"
                  color={data.current.failed_requests ? 'danger' : 'success'}
                />
              </section>
              <div className={styles.context}>
                <span>
                  Чат: <strong>{number(data.current.chat_requests)}</strong>
                </span>
                <span>
                  Shadow API:{' '}
                  <strong>{number(data.current.shadow_requests)}</strong>
                </span>
                <span>
                  Ошибок:{' '}
                  <strong>{number(data.current.failed_requests)}</strong> /{' '}
                  {number(
                    data.current.completed_requests +
                      data.current.failed_requests
                  )}{' '}
                  завершённых запросов
                </span>
              </div>
              <div className={styles.overview}>
                <EntityCard
                  title="Динамика обращений"
                  actions={
                    <span className={styles.hint}>
                      {days === 1 ? 'По часам' : 'По дням'} · UTC
                    </span>
                  }
                >
                  <UsageChart
                    key={days}
                    buckets={data.timeline}
                    hourly={days === 1}
                  />
                </EntityCard>
                {data.problems.length > 0 && (
                  <EntityCard
                    title="Требует внимания"
                    actions={<Badge tone="warn">{data.problems.length}</Badge>}
                  >
                    <div className={styles.problems}>
                      {data.problems.map(problem => (
                        <Link
                          to={problem.href}
                          key={problem.key}
                          className={styles.problem}
                        >
                          <div className={styles['problem-main']}>
                            <strong>{problem.title}</strong>
                            <span>
                              {problem.detail}
                              {problem.last_at
                                ? ` · ${timestamp(problem.last_at)}`
                                : ''}
                            </span>
                          </div>
                          <Badge
                            tone={
                              problem.severity === 'danger' ? 'danger' : 'warn'
                            }
                          >
                            {number(problem.count)}
                          </Badge>
                          <span aria-hidden="true">→</span>
                        </Link>
                      ))}
                    </div>
                  </EntityCard>
                )}
              </div>
              <DashboardTables data={data} />
              <p className={styles.footer}>
                Песочница исключена из статистики. Один запрос может включать
                несколько запусков агентов и вызовов моделей.
                {data.problems.length === 0 &&
                  ' По текущим проверкам проблем не обнаружено.'}
              </p>
            </>
          )}
        </div>
      </Tab>
    </EntityPageV2>
  );
}

export default DashboardPage;
