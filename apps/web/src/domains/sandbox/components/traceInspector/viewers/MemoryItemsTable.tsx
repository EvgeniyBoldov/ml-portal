import { useEffect, useState } from 'react';

import Button from '@/shared/ui/Button';
import { SmartViewerModal } from '@/shared/ui/SmartViewer';
import { Table, type TableColumn } from '@/shared/ui/Table';
import type { TraceMemoryContextItem } from '@/domains/sandbox/traceProjection';

import styles from './MemoryItemsTable.module.css';

const friendlyFactLabels: Record<string, string> = {
  current_date: 'Текущая дата',
};

type MemoryRow = {
  id: string;
  label: string;
  value: string;
  extra: string;
  detail?: unknown;
  sourceKey?: string;
};

function toRow(item: TraceMemoryContextItem, index: number): MemoryRow {
  const id = `${item.type}:${index}`;
  if (item.type === 'fact') {
    const friendlyLabel = friendlyFactLabels[item.subject];
    return {
      id,
      label: friendlyLabel ?? item.subject,
      value: item.value,
      extra: item.scope,
      sourceKey: friendlyLabel ? item.subject : undefined,
      detail: item.value.length > 160 ? item.value : undefined,
    };
  }
  if (item.type === 'glossary')
    return {
      id,
      label: item.term,
      value: item.description || 'Определение не запрашивалось',
      extra: item.aliases.join(', '),
      detail: item.description.length > 160 ? item.description : undefined,
    };
  if (item.type === 'project')
    return {
      id,
      label: item.key,
      value: item.name,
      extra: item.matchedAliases.join(', '),
    };
  return {
    id,
    label: item.subject,
    value: item.value,
    extra: item.kind,
    detail: item.raw ?? item,
  };
}

/** Compact semantic rows shared by executor memory and memory tool results. */
export function MemoryItemsTable({
  items,
  showScope = false,
  previewLimit,
}: {
  items: TraceMemoryContextItem[];
  showScope?: boolean;
  previewLimit?: number;
}) {
  const [selected, setSelected] = useState<MemoryRow | null>(null);
  const [showAll, setShowAll] = useState(false);
  useEffect(() => {
    const closeDetails = () => setSelected(null);
    document.addEventListener('agent-inspector-section-change', closeDetails);
    return () =>
      document.removeEventListener(
        'agent-inspector-section-change',
        closeDetails
      );
  }, []);
  const type = items[0]?.type;
  const allRows = items.map(toRow);
  const rows =
    previewLimit && !showAll ? allRows.slice(0, previewLimit) : allRows;
  const columns: TableColumn<MemoryRow>[] = [
    {
      key: 'label',
      title:
        type === 'glossary'
          ? 'Термин'
          : type === 'project'
            ? 'Ключ'
            : 'Свойство',
      dataIndex: 'label',
      className: styles.subject,
    },
    {
      key: 'value',
      title:
        type === 'glossary'
          ? 'Определение'
          : type === 'project'
            ? 'Название'
            : type === 'knowledge'
              ? 'Содержание'
              : 'Значение',
      render: (_, row) => (
        <>
          <div
            className={row.detail !== undefined ? styles.preview : styles.value}
          >
            {row.value}
          </div>
          {row.sourceKey ? (
            <details className={styles.keyDetails}>
              <summary>Исходный ключ</summary>
              <code>{row.sourceKey}</code>
            </details>
          ) : null}
        </>
      ),
    },
  ];
  if (
    type === 'knowledge' ||
    showScope ||
    (type !== 'fact' && rows.some(row => row.extra))
  ) {
    columns.push({
      key: 'extra',
      title: type === 'knowledge' ? 'Тип' : showScope ? 'Область' : 'Алиасы',
      dataIndex: 'extra',
      className: styles.extra,
    });
  }
  if (rows.some(row => row.detail !== undefined)) {
    columns.push({
      key: 'details',
      title: 'Просмотр',
      render: (_, row) =>
        row.detail !== undefined ? (
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Подробнее: ${row.label}`}
            onClick={() => setSelected(row)}
          >
            Подробнее
          </Button>
        ) : null,
    });
  }
  return (
    <>
      <Table
        columns={columns}
        data={rows}
        rowKey="id"
        size="small"
        className={styles.table}
      />
      {previewLimit && allRows.length > previewLimit ? (
        <button
          type="button"
          className={styles.showMore}
          aria-expanded={showAll}
          onClick={() => setShowAll(value => !value)}
        >
          {showAll
            ? 'Свернуть список'
            : `Показать ещё ${allRows.length - previewLimit}`}
        </button>
      ) : null}
      {selected ? (
        <SmartViewerModal
          value={selected.detail}
          title={selected.label}
          open
          onClose={() => setSelected(null)}
        />
      ) : null}
    </>
  );
}
