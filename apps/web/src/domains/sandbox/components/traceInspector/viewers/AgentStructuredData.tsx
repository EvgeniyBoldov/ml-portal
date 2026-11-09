import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { JSONDisplay, Modal } from '@/shared/ui';
import { InspectorSection, InspectorTable } from '../InspectorPrimitives';
import { toolDataLabel, toolDataValuePreview } from '../../../toolDataPresentation';
import styles from './AgentStructuredData.module.css';

const PREVIEW_LIMIT = 10;
const MAX_COLUMNS = 4;
const AGENT_DATA_LABELS: Record<string, string> = {
  notes: 'Примечания',
  source_total: 'Всего в источнике',
  data_completeness: 'Полнота данных',
  device_types: 'Типы устройств',
  total_devices: 'Всего устройств',
  count: 'Количество',
  type: 'Тип',
  'missing types': 'Недостающие типы',
  missing_types: 'Недостающие типы',
  'data completeness': 'Полнота данных',
};

function agentDataLabel(key: string): string {
  return AGENT_DATA_LABELS[key.toLowerCase()] ?? toolDataLabel(key);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function renderValue(value: unknown): ReactNode {
  if (value === null) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    if (value.length <= 240) return value;
    return <span className={styles.longText}>
      {value.slice(0, 240)}…
      <details><summary>Показать полностью</summary><span className={styles.fullText}>{value}</span></details>
    </span>;
  }
  return toolDataValuePreview(value);
}

const isSimpleValue = (value: unknown): boolean => value === null
  || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean';

function RecordTable({ rows, columns }: { rows: Array<Record<string, unknown>>; columns: string[] }) {
  return <InspectorTable headers={columns.map(agentDataLabel)} compact>
    {rows.map((row, index) => <tr key={index}>
      {columns.map((key) => <td key={key}>{renderValue(row[key])}</td>)}
    </tr>)}
  </InspectorTable>;
}

function ObjectFields({ entries, depth }: { entries: Array<[string, unknown]>; depth: number }) {
  const shortValues = entries.filter(([, value]) => !isRecord(value) && !Array.isArray(value)
    && !(typeof value === 'string' && value.length > 100));
  const longText = entries.filter(([, value]) => typeof value === 'string' && value.length > 100);
  const complexValues = entries.filter(([, value]) => isRecord(value) || Array.isArray(value));

  return <div className={styles.objectGroups}>
    {shortValues.length ? <dl className={styles.object}>
      {shortValues.map(([key, item]) => <div className={styles.entry} key={key}>
        <dt>{agentDataLabel(key)}</dt><dd>{renderValue(item)}</dd>
      </div>)}
    </dl> : null}
    {complexValues.length ? <div className={styles.complexGroups}>
      {complexValues.map(([key, item]) => <section className={styles.complexGroup} key={key}>
        <h5>{agentDataLabel(key)}</h5>
        <ValuePreview value={item} depth={depth + 1} />
      </section>)}
    </div> : null}
    {longText.length ? <div className={styles.longFields}>
      {longText.map(([key, value]) => <details className={styles.longField} key={key}>
        <summary>{agentDataLabel(key)} · Показать полный текст</summary>
        <p>{value as string}</p>
      </details>)}
    </div> : null}
  </div>;
}

function ValuePreview({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (depth >= 2 && (isRecord(value) || Array.isArray(value))) {
    const count = Array.isArray(value) ? value.length : Object.keys(value).length;
    const kind = Array.isArray(value) ? 'элементов' : 'полей';
    return <details className={styles.deepDetails}>
      <summary>Показать вложенные данные · {count} {kind}</summary>
      <ValuePreview value={value} depth={0} />
    </details>;
  }
  if (Array.isArray(value) && value.every((item) => !isRecord(item) && !Array.isArray(item))) {
    if (!value.length) return <span className={styles.emptyValue}>Пустой список</span>;
    const shown = value.slice(0, PREVIEW_LIMIT);
    return <>
      <ul className={styles.scalarList}>{shown.map((item, index) => <li key={index}>{renderValue(item)}</li>)}</ul>
      {value.length > shown.length ? <details className={styles.more}>
        <summary>Показать ещё {value.length - shown.length}</summary>
        <ul className={styles.scalarList}>{value.slice(PREVIEW_LIMIT).map((item, index) => <li key={index + PREVIEW_LIMIT}>{renderValue(item)}</li>)}</ul>
      </details> : null}
    </>;
  }

  if (Array.isArray(value) && value.length > 0 && value.every(isRecord)) {
    const allColumns = [...new Set(value.flatMap((row) => Object.keys(row)))];
    const columns = allColumns.slice(0, MAX_COLUMNS);
    const shown = value.slice(0, PREVIEW_LIMIT);
    const rest = value.slice(PREVIEW_LIMIT);
    if (!value.every((row) => Object.keys(row).length > 0 && Object.values(row).every(isSimpleValue))) {
      return <div className={styles.recordGroups}>
        {shown.map((row, index) => <section className={styles.recordGroup} key={index}>
          <h5>Запись {index + 1}</h5>
          <ValuePreview value={row} depth={depth} />
        </section>)}
        {rest.length ? <details className={styles.more}>
          <summary>Показать ещё {rest.length} записей</summary>
          <div className={styles.recordGroups}>{rest.map((row, index) => <section className={styles.recordGroup} key={index + PREVIEW_LIMIT}>
            <h5>Запись {index + PREVIEW_LIMIT + 1}</h5>
            <ValuePreview value={row} depth={depth} />
          </section>)}</div>
        </details> : null}
      </div>;
    }
    return <div>
      <RecordTable rows={shown} columns={columns} />
      {rest.length ? <details className={styles.more}>
        <summary>Показать ещё {rest.length} записей</summary>
        <RecordTable rows={rest} columns={columns} />
      </details> : null}
      {allColumns.length > columns.length ? <details className={styles.more}>
        <summary>Показать ещё {allColumns.length - columns.length} полей</summary>
        <RecordTable rows={shown} columns={allColumns.slice(MAX_COLUMNS)} />
        {rest.length ? <RecordTable rows={rest} columns={allColumns.slice(MAX_COLUMNS)} /> : null}
      </details> : null}
    </div>;
  }

  if (isRecord(value)) {
    const entries = Object.entries(value);
    if (!entries.length) return <span className={styles.emptyValue}>Пустой объект</span>;
    const shown = entries.slice(0, PREVIEW_LIMIT);
    const rest = entries.slice(PREVIEW_LIMIT);
    return <>
      <ObjectFields entries={shown} depth={depth} />
      {rest.length ? <details className={styles.more}>
        <summary>Показать ещё {rest.length} полей</summary>
        <ObjectFields entries={rest} depth={depth} />
      </details> : null}
    </>;
  }

  if (Array.isArray(value)) {
    if (!value.length) return <span className={styles.emptyValue}>Пустой список</span>;
    const shown = value.slice(0, PREVIEW_LIMIT);
    return <>
      <ol className={styles.nestedList}>{shown.map((item, index) => <li key={index}>
        {Array.isArray(item) || isRecord(item) ? <ValuePreview value={item} depth={depth + 1} /> : renderValue(item)}
      </li>)}</ol>
      {value.length > shown.length ? <details className={styles.more}>
        <summary>Показать ещё {value.length - shown.length} элементов</summary>
        <ol className={styles.nestedList}>{value.slice(PREVIEW_LIMIT).map((item, index) => <li key={index + PREVIEW_LIMIT}>
          {Array.isArray(item) || isRecord(item) ? <ValuePreview value={item} depth={depth + 1} /> : renderValue(item)}
        </li>)}</ol>
      </details> : null}
    </>;
  }

  return <span className={styles.scalar}>{renderValue(value)}</span>;
}

export function AgentStructuredData({ value, title = 'Структурированные данные' }: { value: unknown; title?: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [mode, setMode] = useState<'human' | 'json'>('human');
  useEffect(() => {
    const close = () => setIsOpen(false);
    document.addEventListener('agent-inspector-section-change', close);
    return () => document.removeEventListener('agent-inspector-section-change', close);
  }, []);
  let rawValue: string;
  try { rawValue = JSON.stringify(value, null, 2) ?? String(value); }
  catch { rawValue = String(value); }
  return <InspectorSection title={title}>
    <div className={styles.preview}>
      <ValuePreview value={value} />
      <button type="button" className={styles.expand} onClick={() => setIsOpen(true)}>
        Открыть все данные
      </button>
    </div>
    <Modal open={isOpen} onClose={() => setIsOpen(false)} title={title} size="xl">
      <div className={styles.fullView}>
        <div className={styles.viewModes} role="group" aria-label="Режим просмотра данных">
          <button type="button" aria-pressed={mode === 'human'} onClick={() => setMode('human')}>Понятный вид</button>
          <button type="button" aria-pressed={mode === 'json'} onClick={() => setMode('json')}>JSON</button>
        </div>
        {mode === 'human' ? <div className={styles.fullHuman}><ValuePreview value={value} /></div> : <JSONDisplay value={rawValue} showExpand />}
      </div>
    </Modal>
  </InspectorSection>;
}
