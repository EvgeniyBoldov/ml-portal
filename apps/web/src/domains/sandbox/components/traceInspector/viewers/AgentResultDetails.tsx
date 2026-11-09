import { buildArtifactDownloadUrl } from '@/shared/api/files';
import type { ReactNode } from 'react';
import Badge from '@/shared/ui/Badge';
import { InspectorSection } from '../InspectorPrimitives';
import type {
  TraceAgentArtifactView,
  TraceAgentDiagnosticView,
  TraceAgentNeedView,
  TraceAgentSourceView,
} from '../../../traceProjection';
import styles from './AgentResultDetails.module.css';

const PREVIEW_LIMIT = 10;

function BoundedList<T>({
  items,
  renderItem,
  className,
}: {
  items: T[];
  renderItem: (item: T, index: number) => ReactNode;
  className?: string;
}) {
  const shown = items.slice(0, PREVIEW_LIMIT);
  const rest = items.slice(PREVIEW_LIMIT);
  return <>
    <ul className={`${styles.list} ${className ?? ''}`}>{shown.map(renderItem)}</ul>
    {rest.length ? <details className={styles.more}>
      <summary>Показать ещё {rest.length}</summary>
      <ul className={`${styles.list} ${className ?? ''}`}>{rest.map((item, index) => renderItem(item, index + PREVIEW_LIMIT))}</ul>
    </details> : null}
  </>;
}

function formatSize(sizeBytes?: number): string | undefined {
  if (sizeBytes === undefined || !Number.isFinite(sizeBytes) || sizeBytes < 0) return undefined;
  if (sizeBytes < 1024) return `${sizeBytes} Б`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} КБ`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} МБ`;
}

export function AgentFiles({ items }: { items: TraceAgentArtifactView[] }) {
  if (!items.length) return null;
  return <InspectorSection title="Файлы">
    <BoundedList items={items} renderItem={(item) => <li key={item.artifactId}>
      <a href={buildArtifactDownloadUrl(item.artifactId)} target="_blank" rel="noopener noreferrer">{item.fileName}</a>
      {item.description ? <span className={styles.meta}>{item.description}</span> : null}
      <span className={styles.meta}>{[item.contentType, formatSize(item.sizeBytes)].filter(Boolean).join(' · ')}</span>
    </li>} />
  </InspectorSection>;
}

function safeSourceHref(value: string | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if ((url.protocol === 'http:' || url.protocol === 'https:') && !url.username && !url.password) return url.href;
  } catch { /* A source without a safe absolute URL stays as plain text. */ }
  return undefined;
}

export function AgentSources({ items }: { items: TraceAgentSourceView[] }) {
  if (!items.length) return null;
  return <InspectorSection title="Источники">
    <BoundedList items={items} renderItem={(item, index) => {
      const href = safeSourceHref(item.href);
      return <li key={`${item.label}:${index}`}>{href
        ? <a href={href} target="_blank" rel="noopener noreferrer">{item.label}</a>
        : <span>{item.label}</span>}</li>;
    }} />
  </InspectorSection>;
}

export function AgentNeeds({ items }: { items: TraceAgentNeedView[] }) {
  if (!items.length) return null;
  return <InspectorSection title="Для продолжения нужно">
    <BoundedList items={items} className={styles.needList} renderItem={(item, index) => <li className={styles.needCard} key={`${item.description}:${index}`}>
      <span className={styles.needDescription}>{item.description}</span>
      <span className={styles.needBadges}>
        {item.kind ? <Badge size="small" tone="info">{item.kind === 'artifact' ? 'Файл' : item.kind === 'decision' ? 'Решение' : 'Данные'}</Badge> : null}
        {item.required !== undefined ? <Badge size="small" tone={item.required ? 'warn' : 'neutral'}>{item.required ? 'Обязательно' : 'Необязательно'}</Badge> : null}
      </span>
    </li>} />
  </InspectorSection>;
}

export function AgentDiagnostics({ items }: { items: TraceAgentDiagnosticView[] }) {
  if (!items.length) return null;
  return <InspectorSection title="Замечания к формату">
    <BoundedList items={items} className={styles.diagnosticList} renderItem={(item) => <li className={styles.diagnosticCard} key={item.label}>
      <div className={styles.diagnosticHeading}><span>{item.label}</span><Badge size="small" tone="warn">{item.count}</Badge></div>
      {item.details?.length ? <details className={styles.diagnosticDetails}>
        <summary>Что это значит</summary>
        {item.details.map((detail, index) => <p key={`${detail}:${index}`}>{detail}</p>)}
      </details> : null}
    </li>} />
  </InspectorSection>;
}
