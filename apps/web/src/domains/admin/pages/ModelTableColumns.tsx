import { Badge, type DataTableColumn } from '@/shared/ui';
import type { Model } from '@/shared/api/admin';
import styles from './ModelTableColumns.module.css';

export const modelTableColumns: DataTableColumn<Model>[] = [
  {
    key: 'alias',
    label: 'АЛИАС / НАЗВАНИЕ',
    sortable: true,
    render: (m: Model) => (
      <div className={styles.identity}>
        <span className={styles['primary-label']}>{m.alias}</span>
        <span className={styles['secondary-label']}>{m.name}</span>
      </div>
    ),
  },
  {
    key: 'type',
    label: 'ТИП',
    width: 110,
    render: (m: Model) => {
      const toneMap: Record<string, 'info' | 'success' | 'warn'> = {
        llm_chat: 'info',
        embedding: 'success',
        reranker: 'warn',
      };
      const labelMap: Record<string, string> = {
        llm_chat: 'LLM Chat',
        embedding: 'Embedding',
        reranker: 'Reranker',
      };
      return (
        <Badge tone={toneMap[m.type] ?? 'info'}>
          {labelMap[m.type] ?? m.type}
        </Badge>
      );
    },
  },
  {
    key: 'connector',
    label: 'КОННЕКТОР',
    sortable: true,
    render: (m: Model) => (
      <div className={styles.identity}>
        <span className={styles['primary-label']}>{m.connector}</span>
        <span className={styles['secondary-label']}>
          {m.provider_model_name}
        </span>
      </div>
    ),
  },
  {
    key: 'enabled',
    label: 'ИСПОЛЬЗОВАНИЕ',
    width: 135,
    filter: {
      kind: 'select',
      placeholder: 'Все модели',
      options: [
        { value: 'enabled', label: 'Включена' },
        { value: 'disabled', label: 'Выключена' },
      ],
      getValue: m => (m.enabled ? 'enabled' : 'disabled'),
    },
    render: m => (
      <Badge
        tone={m.enabled ? 'success' : 'neutral'}
        size="small"
        title={
          m.enabled
            ? 'Разрешено использование платформой'
            : 'Отключена в платформе; сам сервис может продолжать работать'
        }
      >
        {m.enabled ? 'Включена' : 'Выключена'}
      </Badge>
    ),
  },
  {
    key: 'status',
    label: 'СТАТУС МОДЕЛИ',
    width: 120,
    render: (m: Model) => {
      const toneMap: Record<string, 'success' | 'warn' | 'danger' | 'neutral'> =
        {
          available: 'success',
          unavailable: 'danger',
          deprecated: 'neutral',
          maintenance: 'warn',
        };
      const labelMap: Record<string, string> = {
        available: 'Доступна',
        unavailable: 'Недоступна',
        deprecated: 'Устарела',
        maintenance: 'Обслуживание',
      };
      return (
        <Badge tone={toneMap[m.status] ?? 'neutral'}>
          {labelMap[m.status] ?? m.status}
        </Badge>
      );
    },
  },
  {
    key: 'health_status',
    label: 'ПРОВЕРКА СЕРВИСА',
    width: 155,
    render: m => {
      const health = m.health_status;
      const label =
        health === 'healthy'
          ? 'Работает'
          : health === 'degraded'
            ? 'С ошибками'
            : health === 'unavailable'
              ? 'Недоступен'
              : 'Не проверено';
      return (
        <Badge
          size="small"
          tone={
            health === 'healthy'
              ? 'success'
              : health === 'degraded'
                ? 'warn'
                : health === 'unavailable'
                  ? 'danger'
                  : 'neutral'
          }
          title={
            m.last_health_check_at
              ? `Проверено: ${new Date(m.last_health_check_at).toLocaleString()}`
              : undefined
          }
        >
          {label}
          {m.health_latency_ms != null && health
            ? ` · ${m.health_latency_ms} мс`
            : ''}
        </Badge>
      );
    },
  },
  {
    key: 'default_for_type',
    label: 'ПО УМОЛЧ.',
    width: 100,
    render: (m: Model) =>
      m.default_for_type ? (
        <Badge
          tone={m.enabled ? 'success' : 'neutral'}
          title={m.enabled ? undefined : 'Назначена по умолчанию, но выключена'}
        >
          По умолч.
        </Badge>
      ) : (
        <span className={styles['secondary-label']}>—</span>
      ),
  },
];
