import { Badge, Button, Checkbox, Input, Select } from '@/shared/ui';
import type { CollectionField, CollectionType, SearchMode } from '@/shared/api';
import { SQL_SPECIFIC_FIELD_NAMES } from './collectionFieldPresets';

const FIELD_TYPES = ['text', 'integer', 'float', 'boolean', 'datetime', 'date', 'file'] as const;
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
  const isLockedSpecificField = (field: CollectionField) =>
    collectionType === 'sql' && SQL_SPECIFIC_FIELD_NAMES.has(field.name);

  const add = () => onChange([...fields, emptyField()]);

  const remove = (i: number) => {
    if (isLockedSpecificField(fields[i])) return;
    onChange(fields.filter((_, idx) => idx !== i));
  };

  const update = (i: number, patch: Partial<CollectionField>) =>
    onChange(fields.map((f, idx) => {
      if (idx !== i) return f;
      if (isLockedSpecificField(f)) return f;
      return { ...f, ...patch };
    }));

  const toggleMode = (i: number, mode: SearchMode) => {
    if (isLockedSpecificField(fields[i])) return;
    const modes = fields[i].search_modes;
    update(i, { search_modes: modes.includes(mode) ? modes.filter((m) => m !== mode) : [...modes, mode] });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {fields.map((f, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 140px 80px 1fr auto', gap: '0.5rem', alignItems: 'center', padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
          {isLockedSpecificField(f) && (
            <div style={{ gridColumn: '1 / -1', marginBottom: '0.25rem' }}>
              <Badge tone="info">Обязательное системное поле SQL (только чтение)</Badge>
            </div>
          )}
          <Input
            placeholder="название поля"
            value={f.name}
            onChange={(e) => update(i, { name: e.target.value })}
            disabled={isLockedSpecificField(f)}
          />
          <Select
            value={f.type}
            onChange={(value) => update(i, { type: value as CollectionField['type'] })}
            options={FIELD_TYPES.map((t) => ({ value: t, label: t }))}
            disabled={isLockedSpecificField(f)}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <Checkbox
              checked={f.required}
              onChange={(checked) => update(i, { required: checked })}
              disabled={isLockedSpecificField(f)}
            />
            <span style={{ fontSize: '0.875rem' }}>Обяз.</span>
          </div>
          <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
            {SEARCH_MODES.map((m) => (
              <div key={m} style={{ display: 'flex', alignItems: 'center', gap: '0.125rem' }}>
                <Checkbox
                  checked={f.search_modes.includes(m)}
                  onChange={() => toggleMode(i, m)}
                  disabled={isLockedSpecificField(f)}
                />
                <Badge tone="info">{m}</Badge>
              </div>
            ))}
          </div>
          <Button variant="danger" size="sm" onClick={() => remove(i)} disabled={isLockedSpecificField(f)}>×</Button>
        </div>
      ))}
      <div>
        <Button variant="outline" size="sm" onClick={add}>+ Добавить поле</Button>
      </div>
    </div>
  );
}
