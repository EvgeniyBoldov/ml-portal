/**
 * useEntityFields - Hook for generating dynamic entity fields based on mode
 * 
 * Provides consistent field definitions across all entity editors:
 * - slug: editable only in create mode
 * - name: always editable in edit/create modes
 * - description: always editable in edit/create modes
 */
import { type FieldDefinition } from '@/shared/ui/ContentBlock/ContentBlock';
import { type EntityPageMode } from '@/shared/ui/EntityPage/EntityPageV2';

export interface EntityFieldsOptions {
  /** Additional fields to include after standard fields */
  additionalFields?: FieldDefinition[];
  /** Custom label for slug field */
  slugLabel?: string;
  /** Whether to include description field */
  includeDescription?: boolean;
  /** Custom description field configuration */
  descriptionField?: Partial<FieldDefinition>;
}

/**
 * Returns field definitions for entity based on mode
 * 
 * @param mode - Current entity page mode
 * @param options - Additional configuration options
 * @returns Array of field definitions
 */
export function useEntityFields(mode: EntityPageMode, options: EntityFieldsOptions = {}): FieldDefinition[] {
  const {
    additionalFields = [],
    slugLabel = 'Slug (ID)',
    includeDescription = true,
    descriptionField = {},
  } = options;

  const baseFields: FieldDefinition[] = [
    { 
      key: 'slug', 
      label: slugLabel, 
      type: 'text', 
      required: true, 
      disabled: mode !== 'create'  // Only editable in create mode
    },
    { key: 'name', label: 'Название', type: 'text', required: true },
  ];

  // Add description field if enabled
  if (includeDescription) {
    baseFields.push({
      key: 'description', 
      label: 'Описание', 
      type: 'textarea', 
      rows: 2,
      ...descriptionField,
    });
  }

  return [...baseFields, ...additionalFields];
}
