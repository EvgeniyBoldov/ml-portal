import { useEffect, useMemo, useState } from 'react';
import { SmartViewer, SmartViewerModal } from '@/shared/ui/SmartViewer';
import { InspectorEmptyState } from '../InspectorPrimitives';
import styles from './RawEventsViewer.module.css';

export type RawTraceEvent = { sequence: number; eventType: string; value: unknown };

function filterValue(value: unknown, query: string): unknown {
  if (!query) return value;
  const normalized = query.toLocaleLowerCase();
  if (value === null || ['string', 'number', 'boolean'].includes(typeof value)) {
    return String(value).toLocaleLowerCase().includes(normalized) ? value : undefined;
  }
  if (Array.isArray(value)) {
    const matches = value.map(item => filterValue(item, query)).filter(item => item !== undefined);
    return matches.length ? matches : undefined;
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value).flatMap(([key, item]) => {
      const match = filterValue(item, query);
      return key.toLocaleLowerCase().includes(normalized) || match !== undefined ? [[key, key.toLocaleLowerCase().includes(normalized) && match === undefined ? item : match] as const] : [];
    });
    return entries.length ? Object.fromEntries(entries) : undefined;
  }
  return undefined;
}

function serialize(value: unknown): string {
  try {
    return JSON.stringify(value) ?? String(value);
  } catch {
    return String(value);
  }
}

export function RawEventsViewer({ events }: { events: RawTraceEvent[] }) {
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<RawTraceEvent | null>(null);
  useEffect(() => {
    const handleSectionChange = () => setSelected(null);
    document.addEventListener('agent-inspector-section-change', handleSectionChange);
    return () => document.removeEventListener('agent-inspector-section-change', handleSectionChange);
  }, []);
  const visibleEvents = useMemo(() => events.filter(event => !search.trim() || (event.eventType + ' ' + serialize(event.value)).toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())), [events, search]);
  if (!events.length) return <InspectorEmptyState message="В журнале нет событий для этой записи." />;

  return <div className={styles.root}>
    <label className={styles.search}>Поиск по событиям и данным<input value={search} onChange={event => setSearch(event.target.value)} placeholder="Тип, ключ или значение" /></label>
    <div className={styles.events}>
      {visibleEvents.map(event => {
        const filtered = filterValue(event.value, search.trim());
        const shownValue = search.trim() && filtered !== undefined ? filtered : event.value;
        const hasMatch = filtered !== undefined;
        return <details className={styles.event} key={event.sequence + ':' + event.eventType}>
          <summary><span className={styles.sequence}>#{event.sequence}</span><span className={styles.type}>{event.eventType}</span></summary>
          <div className={styles.payload}>
            {search.trim() && !hasMatch ? <p className={styles.noMatch}>В этом событии совпадений в содержимом нет; исходные данные сохранены.</p> : null}
            <SmartViewer value={shownValue} />
            {search.trim() && hasMatch ? <p className={styles.filterNote}>Показаны совпавшие поля. Полный payload доступен в просмотре.</p> : null}
            <button type="button" className={styles.fullView} onClick={() => setSelected(event)}>Открыть полный payload</button>
          </div>
        </details>;
      })}
      {!visibleEvents.length ? <p className={styles.noMatch}>Событий по запросу не найдено.</p> : null}
    </div>
    {selected ? <SmartViewerModal value={selected.value} open onClose={() => setSelected(null)} title={'Событие #' + selected.sequence + ' · ' + selected.eventType} /> : null}
  </div>;
}
