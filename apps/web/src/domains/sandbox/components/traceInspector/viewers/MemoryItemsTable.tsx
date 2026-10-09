import { useState } from 'react';

import Button from '@/shared/ui/Button';
import { SmartViewerModal } from '@/shared/ui/SmartViewer';
import { Table, type TableColumn } from '@/shared/ui/Table';
import type { TraceMemoryContextItem } from '@/domains/sandbox/traceProjection';

import styles from './MemoryItemsTable.module.css';

type MemoryRow = {
  id: string;
  label: string;
  value: string;
  extra: string;
  detail?: unknown;
};

function toRow(item: TraceMemoryContextItem, index: number): MemoryRow {
  const id = `${item.type}:${index}`;
  if (item.type === 'fact')
    return {
      id,
      label: item.subject,
      value: item.value,
      extra: item.scope,
      detail: item.value.length > 160 ? item.value : undefined,
    };
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
}: {
  items: TraceMemoryContextItem[];
  showScope?: boolean;
}) {
  const [selected, setSelected] = useState<MemoryRow | null>(null);
  const type = items[0]?.type;
  const rows = items.map(toRow);
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
        <div
          className={row.detail !== undefined ? styles.preview : styles.value}
        >
          {row.value}
        </div>
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
