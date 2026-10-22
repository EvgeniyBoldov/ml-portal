import React, { useState } from 'react';
import type { UsageBucket } from '@/shared/api/dashboard';
import { number } from './format';
import styles from './UsageChart.module.css';

export function UsageChart({
  buckets,
  hourly,
}: {
  buckets: UsageBucket[];
  hourly: boolean;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const max = Math.max(1, ...buckets.map(bucket => bucket.requests));
  const width = 1000;
  const height = 160;
  const slot = width / Math.max(1, buckets.length);
  const date = (value: string) =>
    new Date(value).toLocaleString('ru-RU', {
      timeZone: 'UTC',
      day: '2-digit',
      month: '2-digit',
      ...(hourly ? ({ hour: '2-digit', minute: '2-digit' } as const) : {}),
    });
  const active = selected === null ? null : buckets[selected];
  const hasRequests = buckets.some(bucket => bucket.requests > 0);
  return (
    <div className={styles.chart}>
      <div className={styles.legend}>
        <span>
          <i className={styles['request-key']} />
          Запросы
        </span>
        <span>
          <i className={styles['error-key']} />
          Из них с ошибкой
        </span>
        <span className={styles.selection} aria-live="polite">
          {active
            ? `${date(active.at)} · ${number(active.requests)} запросов · ${number(active.errors)} ошибок`
            : hasRequests
              ? 'Выберите столбец, чтобы увидеть значения'
              : 'За период обращений нет'}
        </span>
      </div>
      <div className={styles.plot}>
        <div className={styles.scale}>
          <span>{number(max)}</span>
          <span>0</span>
        </div>
        <svg
          viewBox={`0 0 ${width} ${height + 10}`}
          preserveAspectRatio="none"
          className={styles.svg}
          role="group"
          aria-label="Запросы и ошибки по времени"
        >
          {[0, 0.5, 1].map(ratio => (
            <line
              key={ratio}
              x1="0"
              x2={width}
              y1={height * ratio + 5}
              y2={height * ratio + 5}
              className={styles['grid-line']}
            />
          ))}
          {buckets.map((bucket, index) => {
            const barHeight = (bucket.requests / max) * height;
            const errorHeight = (bucket.errors / max) * height;
            const label = `${date(bucket.at)}: запросов ${bucket.requests}, ошибок ${bucket.errors}`;
            return (
              <g
                key={bucket.at}
                tabIndex={0}
                role="img"
                aria-label={label}
                onFocus={() => setSelected(index)}
                onBlur={() => setSelected(null)}
                onMouseEnter={() => setSelected(index)}
                onMouseLeave={() => setSelected(null)}
              >
                <title>{label}</title>
                <rect
                  x={index * slot + 2}
                  y="0"
                  width={Math.max(1, slot - 4)}
                  height={height + 10}
                  className={styles['hit-area']}
                />
                <rect
                  x={index * slot + 3}
                  y={height - barHeight + 5}
                  width={Math.max(1, slot - 6)}
                  height={Math.max(0, barHeight)}
                  rx="3"
                  className={styles.bar}
                />
                <rect
                  x={index * slot + 3}
                  y={height - errorHeight + 5}
                  width={Math.max(1, slot - 6)}
                  height={errorHeight}
                  rx="2"
                  className={styles['error-bar']}
                />
              </g>
            );
          })}
        </svg>
      </div>
      <div className={styles.axis}>
        {buckets
          .filter(
            (_, index) =>
              index === 0 ||
              index === Math.floor(buckets.length / 2) ||
              index === buckets.length - 1
          )
          .map(bucket => (
            <span key={bucket.at}>{date(bucket.at)}</span>
          ))}
      </div>
    </div>
  );
}
