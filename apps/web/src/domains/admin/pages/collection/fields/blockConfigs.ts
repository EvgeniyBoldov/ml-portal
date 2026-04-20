import type { CollectionType } from '@/shared/api';
import type { FieldConfig } from '@/shared/ui/GridLayout';

export const COLLECTION_TYPE_OPTIONS = [
  { value: 'table', label: 'Таблица' },
  { value: 'document', label: 'Документы (RAG)' },
  { value: 'sql', label: 'SQL' },
  { value: 'api', label: 'API' },
];

export const INFO_FIELDS: FieldConfig[] = [
  {
    key: 'slug',
    type: 'text',
    label: 'Slug (ID)',
    description: 'Уникальный идентификатор (нельзя изменить после создания)',
    editable: false,
    placeholder: 'customer-data',
  },
  {
    key: 'name',
    type: 'text',
    label: 'Название',
    required: true,
    placeholder: 'Данные клиентов',
  },
  {
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    placeholder: 'Описание коллекции...',
    rows: 3,
  },
  {
    key: 'tenant_id',
    type: 'select',
    label: 'Тенант',
    required: true,
    description: 'Тенант, которому принадлежит коллекция',
    editable: false,
  },
];

const CONFIG_BASE_FIELDS: FieldConfig[] = [
  {
    key: 'collection_type',
    type: 'select',
    label: 'Тип коллекции',
    required: true,
    description: 'Таблица — табличные данные (CSV). Документы — файлы с RAG-пайплайном.',
    editable: false,
    options: COLLECTION_TYPE_OPTIONS,
  },
  {
    key: 'is_active',
    type: 'boolean',
    label: 'Активна',
    description: 'Коллекция доступна для использования',
  },
];

const TABLE_NAME_FIELD: FieldConfig = {
  key: 'table_name',
  type: 'text',
  label: 'Имя таблицы',
  placeholder: 'customer_data',
  description: 'Имя таблицы в базе данных (генерируется автоматически)',
};

const DATA_CONNECTOR_FIELD: FieldConfig = {
  key: 'data_instance_id',
  type: 'select',
  label: 'Коннектор данных',
  required: true,
  description: 'Data-коннектор, через который коллекция получает данные',
  editable: true,
};

type ConfigStrategyCtx = {
  editableCollectionType: boolean;
  connectorOptions: Array<{ value: string; label: string }>;
};

type ConfigStrategy = (ctx: ConfigStrategyCtx) => FieldConfig[];

const CONFIG_FIELDS_BY_TYPE: Record<CollectionType, ConfigStrategy> = {
  table: () => [TABLE_NAME_FIELD],
  document: () => [],
  sql: ({ connectorOptions }) => [{ ...DATA_CONNECTOR_FIELD, options: connectorOptions }],
  api: ({ connectorOptions }) => [{ ...DATA_CONNECTOR_FIELD, options: connectorOptions }],
};

export function buildConfigFieldsByType(
  collectionType: CollectionType,
  ctx: ConfigStrategyCtx,
): FieldConfig[] {
  const strategy = CONFIG_FIELDS_BY_TYPE[collectionType] ?? CONFIG_FIELDS_BY_TYPE.table;
  return [
    {
      ...CONFIG_BASE_FIELDS[0],
      editable: ctx.editableCollectionType,
      options: COLLECTION_TYPE_OPTIONS,
    },
    ...strategy(ctx),
    CONFIG_BASE_FIELDS[1],
  ];
}

export const VECTOR_FIELDS: FieldConfig[] = [
  {
    key: 'has_vector_search',
    type: 'boolean',
    label: 'Векторный поиск',
    description: 'Включить векторизацию и семантический поиск',
  },
  {
    key: 'chunk_strategy',
    type: 'select',
    label: 'Стратегия чанков',
    placeholder: 'by_tokens',
    description: 'Как разбивать текст на чанки для векторизации',
    options: [
      { value: 'by_tokens', label: 'По токенам' },
      { value: 'by_paragraphs', label: 'По параграфам' },
      { value: 'by_sentences', label: 'По предложениям' },
      { value: 'by_markdown', label: 'По Markdown' },
    ],
  },
  {
    key: 'chunk_size',
    type: 'number',
    label: 'Размер чанка',
    placeholder: '500',
    description: 'Количество токенов в одном чанке',
  },
  {
    key: 'overlap',
    type: 'number',
    label: 'Перекрытие',
    placeholder: '50',
    description: 'Количество перекрывающихся токенов между чанками',
  },
];

export const META_FIELDS: FieldConfig[] = [
  { key: 'id', type: 'code', label: 'ID', editable: false },
  { key: 'created_at', type: 'date', label: 'Создана', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлена', editable: false },
];

export const STATS_FIELDS: FieldConfig[] = [
  { key: 'row_count', type: 'badge', label: 'Записей', badgeTone: 'neutral', editable: false },
  { key: 'fields_count', type: 'badge', label: 'Полей', badgeTone: 'info', editable: false },
  { key: 'has_vector_search', type: 'badge', label: 'Vector search', badgeTone: 'success', editable: false },
  { key: 'is_active', type: 'badge', label: 'Активна', badgeTone: 'neutral', editable: false },
];

export const VECTOR_STATS_FIELDS: FieldConfig[] = [
  {
    key: 'total_rows',
    type: 'badge',
    label: 'Всего строк',
    badgeTone: 'neutral',
    editable: false,
  },
  {
    key: 'vectorized_rows',
    type: 'badge',
    label: 'Векторизовано',
    badgeTone: 'success',
    editable: false,
  },
  {
    key: 'total_chunks',
    type: 'badge',
    label: 'Чанков',
    badgeTone: 'info',
    editable: false,
  },
  {
    key: 'failed_rows',
    type: 'badge',
    label: 'Ошибки',
    badgeTone: 'warn',
    editable: false,
  },
  {
    key: 'vectorization_progress',
    type: 'badge',
    label: 'Прогресс',
    badgeTone: 'info',
    editable: false,
    render: (value: number) => `${Math.round(value)}%`,
  },
  {
    key: 'is_fully_vectorized',
    type: 'badge',
    label: 'Готова',
    badgeTone: 'success',
    editable: false,
  },
];

export const STATUS_FIELDS: FieldConfig[] = [
  {
    key: 'status',
    type: 'badge',
    label: 'Статус',
    badgeTone: 'neutral',
    editable: false,
  },
  {
    key: 'qdrant_collection_name',
    type: 'code',
    label: 'Qdrant collection',
    editable: false,
  },
  {
    key: 'status_details',
    type: 'json',
    label: 'Status details',
    editable: false,
  },
];
