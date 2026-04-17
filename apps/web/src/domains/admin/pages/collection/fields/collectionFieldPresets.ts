import type { CollectionField, CollectionType } from '@/shared/api';

export const DOCUMENT_PRESET_FIELDS: CollectionField[] = [
  { name: 'file', type: 'file', required: true, search_modes: ['vector'], description: 'Файл документа' },
  { name: 'title', type: 'text', required: false, search_modes: ['exact', 'like'], description: 'Название документа' },
  { name: 'source', type: 'text', required: false, search_modes: ['exact'], description: 'Источник документа' },
  { name: 'scope', type: 'text', required: false, search_modes: ['exact'], description: 'Область (department, team)' },
  { name: 'tags', type: 'text', required: false, search_modes: ['like'], description: 'Теги через запятую' },
];

export const SQL_PRESET_FIELDS: CollectionField[] = [
  {
    name: 'table_name',
    type: 'text',
    required: true,
    search_modes: [],
    description: 'SQL table name',
    category: 'specific',
    data_type: 'string',
  },
  {
    name: 'table_schema',
    type: 'text',
    required: true,
    search_modes: [],
    description: 'SQL table schema',
    category: 'specific',
    data_type: 'json',
  },
];

export const SQL_SPECIFIC_FIELD_NAMES = new Set(SQL_PRESET_FIELDS.map((field) => field.name));

export function ensureSqlPresetFields(fields: CollectionField[]): CollectionField[] {
  const byName = new Map(fields.map((field) => [field.name, field]));
  const result: CollectionField[] = [];

  for (const preset of SQL_PRESET_FIELDS) {
    result.push({ ...preset, ...(byName.get(preset.name) ?? {}) });
    byName.delete(preset.name);
  }

  for (const field of fields) {
    if (!SQL_SPECIFIC_FIELD_NAMES.has(field.name)) {
      result.push(field);
    }
  }

  return result;
}

export function applyCollectionTypeFieldPreset(
  collectionType: CollectionType,
  currentFields: CollectionField[],
): CollectionField[] {
  switch (collectionType) {
    case 'document':
      return DOCUMENT_PRESET_FIELDS;
    case 'sql':
      return ensureSqlPresetFields(currentFields);
    case 'table':
    case 'api':
    default:
      return [];
  }
}
