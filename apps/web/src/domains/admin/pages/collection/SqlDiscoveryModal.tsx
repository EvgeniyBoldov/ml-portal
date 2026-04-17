import { type CSSProperties } from 'react';
import { Button, Checkbox, Modal } from '@/shared/ui';
import { renderSchemaLines } from './sqlSchema';
import type { SqlDiscoveryItem } from './useSqlCollectionCatalog';

interface SqlDiscoveryModalProps {
  open: boolean;
  onClose: () => void;
  loading: boolean;
  saving: boolean;
  items: SqlDiscoveryItem[];
  selected: Set<string>;
  existingNames: Set<string>;
  onToggle: (key: string, checked: boolean) => void;
  onSubmit: () => void;
}

const schemaBoxStyle: CSSProperties = {
  fontFamily: 'var(--font-mono, monospace)',
  fontSize: '12px',
  lineHeight: 1.35,
  background: 'var(--bg-secondary)',
  border: '1px solid var(--border-color)',
  borderRadius: '6px',
  padding: '0.5rem',
  maxHeight: '120px',
  overflow: 'auto',
  whiteSpace: 'pre-wrap',
};

export function SqlDiscoveryModal({
  open,
  onClose,
  loading,
  saving,
  items,
  selected,
  existingNames,
  onToggle,
  onSubmit,
}: SqlDiscoveryModalProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="SQL discovery таблиц"
      size="lg"
      footer={(
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Отмена
          </Button>
          <Button
            variant="primary"
            onClick={onSubmit}
            disabled={saving || selected.size === 0}
          >
            {saving ? 'Добавление...' : `Добавить (${selected.size})`}
          </Button>
        </div>
      )}
    >
      {loading ? (
        <div style={{ padding: '1rem' }}>Загрузка таблиц...</div>
      ) : (
        <div style={{ maxHeight: 460, overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Выбор</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Таблица</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Тип</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Колонок</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Схема</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const columnCount = Object.keys((item.table_schema?.properties ?? {}) as Record<string, unknown>).length;
                const schemaLines = renderSchemaLines(item.table_schema);
                const checked = selected.has(item.key);
                const fullName = `${item.schema_name}.${item.table_name}`.trim().toLowerCase();
                const alreadyAdded = existingNames.has(fullName);
                return (
                  <tr key={item.key}>
                    <td style={{ padding: '0.5rem' }}>
                      <Checkbox
                        checked={checked}
                        onChange={(next) => onToggle(item.key, next)}
                        disabled={alreadyAdded}
                      />
                    </td>
                    <td style={{ padding: '0.5rem' }}>
                      <code>{item.schema_name}.{item.table_name}</code>
                      {alreadyAdded && (
                        <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 2 }}>
                          Уже добавлена
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '0.5rem' }}>{item.object_type ?? 'TABLE'}</td>
                    <td style={{ padding: '0.5rem' }}>{columnCount}</td>
                    <td style={{ padding: '0.5rem' }}>
                      {schemaLines.length ? (
                        <div style={schemaBoxStyle}>{schemaLines.join('\n')}</div>
                      ) : (
                        <span style={{ color: 'var(--text-secondary)' }}>—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {!items.length && (
                <tr>
                  <td colSpan={5} style={{ padding: '0.75rem', color: 'var(--text-secondary)' }}>
                    Таблицы не найдены
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
