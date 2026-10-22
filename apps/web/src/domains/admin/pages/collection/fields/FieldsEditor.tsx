import { Badge, Button, Checkbox, Input, Select } from '@/shared/ui';
import { ADMIN_ACTION_LABELS, ADMIN_ENTITY_LABELS } from '@/shared/constants/adminLabels';
import type { BackendCollectionField, CollectionField, CollectionType, SearchMode } from '@/shared/api';
import { DOCUMENT_FULLY_LOCKED_FIELD_NAMES, SQL_SPECIFIC_FIELD_NAMES, TEMPLATE_FULLY_LOCKED_FIELD_NAMES } from './collectionFieldPresets';
import styles from './FieldsEditor.module.css';

const FIELD_TYPES: BackendCollectionField['data_type'][] = [
  'string', 'text', 'integer', 'float', 'boolean', 'datetime', 'date', 'enum', 'json', 'file',
];
const SEARCH_MODES: SearchMode[] = ['exact', 'like', 'range', 'vector'];

const emptyField = (): CollectionField => ({
  name: '',
  type: 'text',
  required: false,
  search_modes: [],
  description: '',
});

interface FieldsEditorProps {
  fields: CollectionField[];
  onChange: (fields: CollectionField[]) => void;
  collectionType?: CollectionType;
}

export function FieldsEditor({ fields, onChange, collectionType }: FieldsEditorProps) {
  const isLocked = (field: CollectionField) =>
    (collectionType === 'sql' && SQL_SPECIFIC_FIELD_NAMES.has(field.name))
    || (collectionType === 'document' && DOCUMENT_FULLY_LOCKED_FIELD_NAMES.has(field.name))
    || (collectionType === 'template' && TEMPLATE_FULLY_LOCKED_FIELD_NAMES.has(field.name));

  const add = () => onChange([...fields, emptyField()]);

  const remove = (i: number) => {
    if (isLocked(fields[i])) return;
    onChange(fields.filter((_, idx) => idx !== i));
  };

  const update = (i: number, patch: Partial<CollectionField>) =>
    onChange(fields.map((f, idx) => {
      if (idx !== i) return f;
      if (isLocked(f)) return f;
      return { ...f, ...patch };
    }));

  const toggleMode = (i: number, mode: SearchMode) => {
    if (isLocked(fields[i])) return;
    const modes = fields[i].search_modes;
    const nextModes = modes.includes(mode)
      ? modes.filter((currentMode) => currentMode !== mode)
      : [...modes, mode];
    update(i, {
      search_modes: nextModes,
      filterable: nextModes.includes('exact') || nextModes.includes('like'),
      sortable: nextModes.includes('range'),
      used_in_retrieval: nextModes.includes('vector'),
    });
  };

  const updateType = (i: number, value: string) => {
    const dataType = value as BackendCollectionField['data_type'];
    const field = fields[i];
    const searchModes = field.search_modes.filter((mode) =>
      (mode !== 'vector' || dataType === 'text')
      && (mode !== 'range' || (dataType !== 'file' && dataType !== 'json'))
    );
    update(i, {
      type: dataType,
      data_type: dataType,
      search_modes: searchModes,
      sortable: searchModes.includes('range'),
      used_in_retrieval: searchModes.includes('vector'),
    });
  };

  return (
    <div className={styles.fieldsEditor}>
      {fields.map((f, i) => (
        <div key={f.name || i} className={styles.fieldRow}>
          <Input
            placeholder="название поля"
            value={f.name}
            onChange={(e) => update(i, { name: e.target.value })}
            disabled={isLocked(f)}
          />
          <Select
            value={f.type}
            onChange={(value) => updateType(i, value)}
            options={FIELD_TYPES.map((t) => ({ value: t, label: t }))}
            disabled={isLocked(f)}
          />
          <div className={styles.requiredField}>
            <Checkbox
              checked={f.required}
              onChange={(checked) => update(i, { required: checked })}
              disabled={isLocked(f)}
            />
            <span className={styles.requiredLabel}>Обяз.</span>
          </div>
          <div className={styles.searchModes}>
            {SEARCH_MODES.map((m) => (
              <div key={m} className={styles.searchMode}>
                <Checkbox
                  checked={f.search_modes.includes(m)}
                  onChange={() => toggleMode(i, m)}
                  disabled={
                    isLocked(f)
                    || (m === 'vector' && (f.data_type ?? f.type) !== 'text')
                    || (m === 'range' && ['file', 'json'].includes(f.data_type ?? f.type ?? ''))
                  }
                />
                <Badge tone="info">{m}</Badge>
              </div>
            ))}
          </div>
          <Button variant="danger" size="sm" onClick={() => remove(i)} disabled={isLocked(f)}>×</Button>
        </div>
      ))}
      <div>
        <Button variant="outline" size="sm" onClick={add}>{`${ADMIN_ACTION_LABELS.add} ${ADMIN_ENTITY_LABELS.field}`}</Button>
      </div>
    </div>
  );
}
