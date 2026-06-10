import type { CollectionField, CollectionType } from '@/shared/api';

export const DOCUMENT_PRESET_FIELDS: CollectionField[] = [
  { name: 'file', type: 'file', required: true, search_modes: [], description: 'Файл документа', category: 'specific', data_type: 'file' },
  { name: 'title', type: 'text', required: false, search_modes: [], description: 'Название документа', category: 'specific', data_type: 'text' },
  { name: 'source', type: 'text', required: false, search_modes: [], description: 'Источник документа', category: 'specific', data_type: 'string' },
];

export const TEMPLATE_PRESET_FIELDS: CollectionField[] = [
  { name: 'file', type: 'file', required: true, search_modes: [], description: 'Файл шаблона', category: 'specific', data_type: 'file' },
  { name: 'title', type: 'text', required: false, search_modes: ['exact', 'like'], description: 'Название шаблона', category: 'specific', data_type: 'text', filterable: true, used_in_prompt_context: true },
  { name: 'source', type: 'text', required: true, search_modes: [], description: 'Источник шаблона', category: 'specific', data_type: 'string' },
  { name: 'template_version', type: 'text', required: false, search_modes: [], description: 'Версия шаблона', category: 'specific', data_type: 'string' },
  { name: 'template_schema', type: 'text', required: false, search_modes: [], description: 'JSON схема заполнения шаблона', category: 'specific', data_type: 'json' },
  { name: 'description', type: 'text', required: false, search_modes: ['exact', 'like', 'vector'], description: 'Описание шаблона для поиска', category: 'specific', data_type: 'text', filterable: true, used_in_retrieval: true, used_in_prompt_context: true },
  { name: 'status', type: 'text', required: true, search_modes: ['exact', 'like'], description: 'Статус шаблона', category: 'specific', data_type: 'string', filterable: true },
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
export const DOCUMENT_SPECIFIC_FIELD_NAMES = new Set(DOCUMENT_PRESET_FIELDS.map((field) => field.name));
export const TEMPLATE_SPECIFIC_FIELD_NAMES = new Set(TEMPLATE_PRESET_FIELDS.map((field) => field.name));
export const DOCUMENT_FULLY_LOCKED_FIELD_NAMES = new Set(DOCUMENT_PRESET_FIELDS.map((field) => field.name));
export const TEMPLATE_FULLY_LOCKED_FIELD_NAMES = new Set(TEMPLATE_PRESET_FIELDS.map((field) => field.name));

export function ensureSqlPresetFields(fields: CollectionField[]): CollectionField[] {
  const byName = new Map(fields.map((field) => [field.name, field]));
  const result: CollectionField[] = [];

  for (const preset of SQL_PRESET_FIELDS) {
    result.push({ ...preset, ...(byName.get(preset.name) ?? {}) });
    byName.delete(preset.name);
  }

  for (const field of fields) {
    if (
      !SQL_SPECIFIC_FIELD_NAMES.has(field.name)
      && !DOCUMENT_SPECIFIC_FIELD_NAMES.has(field.name)
      && !TEMPLATE_SPECIFIC_FIELD_NAMES.has(field.name)
    ) {
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
    case 'template':
      return TEMPLATE_PRESET_FIELDS;
    case 'sql':
      return ensureSqlPresetFields(currentFields);
    case 'table':
    case 'api':
    default:
      return [];
  }
}
