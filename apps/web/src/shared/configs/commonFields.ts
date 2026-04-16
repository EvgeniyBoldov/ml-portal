/**
 * Common field configurations for all entities
 */
import type { FieldConfig } from '../ui/GridLayout';

// Базовые поля информации (slug, name, description)
export const BASE_INFO_FIELDS: FieldConfig[] = [
  {
    key: 'slug',
    type: 'text',
    label: 'Slug',
    description: 'Уникальный идентификатор (нельзя изменить после создания)',
    editable: false,
    disabled: true,
  },
  {
    key: 'name',
    type: 'text',
    label: 'Название',
    required: true,
    placeholder: 'Введите название...',
  },
  {
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    placeholder: 'Введите описание...',
    rows: 3,
  },
];

// Базовые метаданные (id, created_at, updated_at)
export const BASE_META_FIELDS: FieldConfig[] = [
  {
    key: 'id',
    type: 'code',
    label: 'ID',
    editable: false,
    disabled: true,
  },
  {
    key: 'created_at',
    type: 'date',
    label: 'Создан',
    editable: false,
    disabled: true,
  },
  {
    key: 'updated_at',
    type: 'date',
    label: 'Обновлен',
    editable: false,
    disabled: true,
  },
];

// Статусные поля
export const BASE_STATUS_FIELDS: FieldConfig[] = [
  {
    key: 'status',
    type: 'badge',
    label: 'Статус',
    badgeTone: 'info',
    editable: false,
    disabled: true,
  },
  {
    key: 'is_active',
    type: 'boolean',
    label: 'Активен',
    editable: true,
  },
];
