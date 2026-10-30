export type TemplateSchemaNodeKind = 'scalar' | 'object' | 'table';

export interface TemplateSchemaNode {
  key: string;
  path: string;
  label: string;
  kind: TemplateSchemaNodeKind;
  type?: string;
  required: boolean;
  description?: string;
  example?: unknown;
  enum?: unknown[];
  format?: string;
  orientation?: string;
  minRows?: number;
  maxRows?: number | null;
  fields: TemplateSchemaNode[];
}

export interface TemplateSchemaCounts {
  scalarFields: number;
  tables: number;
  tableColumns: number;
  format: string | null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function getLabel(value: Record<string, unknown>, key: string): string {
  const label = value.label ?? value.title ?? value.name;
  return typeof label === 'string' && label.trim() ? label.trim() : key;
}

function getType(value: Record<string, unknown>): string | undefined {
  return typeof value.type === 'string' && value.type.trim() ? value.type.trim() : undefined;
}

function getFields(value: Record<string, unknown>, path: string): TemplateSchemaNode[] {
  if (Array.isArray(value.fields)) {
    return value.fields.flatMap((item) => {
      const field = asRecord(item);
      if (!field) return [];
      return normalizeField(field, path);
    });
  }

  const properties = asRecord(value.properties);
  if (!properties) return [];

  const required = new Set(Array.isArray(value.required)
    ? value.required.filter((key): key is string => typeof key === 'string')
    : []);
  return Object.entries(properties).flatMap(([key, raw]) => {
    const property = asRecord(raw);
    return property ? normalizeField({ ...property, key, required: required.has(key) || property.required === true }, path, true) : [];
  });
}

function normalizeField(
  value: Record<string, unknown>,
  parentPath: string,
  fromJsonSchema = false,
): TemplateSchemaNode[] {
  const keyValue = value.key ?? value.name;
  const key = typeof keyValue === 'string' ? keyValue.trim() : '';
  if (!key) return [];

  const path = parentPath ? `${parentPath}.${key}` : key;
  const type = getType(value);
  let kind: TemplateSchemaNodeKind = value.kind === 'object' || value.kind === 'table'
    ? value.kind
    : 'scalar';
  let childSource = value;

  if (fromJsonSchema && type === 'object' && asRecord(value.properties)) {
    kind = 'object';
    childSource = { properties: value.properties, required: value.required };
  } else if (fromJsonSchema && type === 'array') {
    kind = 'table';
    const items = asRecord(value.items);
    childSource = items ? { properties: items.properties, required: items.required, fields: items.fields } : {};
  }

  const columns = Array.isArray(value.columns) ? value.columns : [];
  if (kind === 'scalar' && columns.length > 0) kind = 'table';

  let fields = getFields(childSource, path);
  if (fields.length === 0 && columns.length > 0) {
    fields = columns.flatMap((rawColumn) => {
      const column = asRecord(rawColumn);
      if (!column) return [];
      const columnKey = column.key ?? column.name;
      return typeof columnKey === 'string'
        ? normalizeField({ ...column, kind: column.kind ?? 'scalar' }, path)
        : [];
    });
  }

  return [{
    key,
    path,
    label: getLabel(value, key),
    kind,
    type,
    required: value.required === true,
    description: typeof value.description === 'string' ? value.description : undefined,
    example: value.example,
    enum: Array.isArray(value.enum) ? value.enum : undefined,
    format: typeof value.format === 'string' ? value.format : undefined,
    orientation: typeof value.orientation === 'string' ? value.orientation : undefined,
    minRows: typeof value.min_rows === 'number' ? value.min_rows : undefined,
    maxRows: value.max_rows === null ? null : typeof value.max_rows === 'number' ? value.max_rows : undefined,
    fields,
  }];
}

export function normalizeTemplateSchema(schema: Record<string, unknown> | null | undefined): TemplateSchemaNode[] {
  if (!schema) return [];
  return getFields(schema, '');
}

export function getTemplateSchemaCounts(schema: Record<string, unknown> | null | undefined): TemplateSchemaCounts {
  const nodes = normalizeTemplateSchema(schema);
  let scalarFields = 0;
  let tables = 0;
  let tableColumns = 0;

  const count = (fields: TemplateSchemaNode[], insideTable = false) => {
    fields.forEach((field) => {
      if (field.kind === 'table') {
        tables += 1;
        count(field.fields, true);
      } else if (field.kind === 'object') {
        count(field.fields, insideTable);
      } else if (insideTable) {
        tableColumns += 1;
      } else {
        scalarFields += 1;
      }
    });
  };

  count(nodes);
  const rawFormat = schema?.format;
  const format = typeof rawFormat === 'string' && rawFormat.trim() ? rawFormat.trim() : null;
  return { scalarFields, tables, tableColumns, format };
}

export function formatTemplateSchemaCounts(counts: TemplateSchemaCounts): string[] {
  const plural = new Intl.PluralRules('ru');
  const word = (count: number, forms: [string, string, string]) => {
    const form = plural.select(count);
    return `${count} ${form === 'one' ? forms[0] : form === 'few' ? forms[1] : forms[2]}`;
  };
  const parts: string[] = [];
  if (counts.scalarFields) parts.push(word(counts.scalarFields, ['поле', 'поля', 'полей']));
  if (counts.tables) parts.push(word(counts.tables, ['таблица', 'таблицы', 'таблиц']));
  if (counts.tableColumns) parts.push(word(counts.tableColumns, ['столбец', 'столбца', 'столбцов']));
  return parts;
}

export function formatTemplateSchemaType(type?: string): string {
  if (!type) return 'Текст';
  const labels: Record<string, string> = {
    bool: 'Да / нет',
    choice: 'Выбор из списка',
    date: 'Дата',
    enum: 'Выбор из списка',
    number: 'Число',
    select: 'Выбор из списка',
    string: 'Текст',
    variant: 'Выбор из списка',
  };
  const normalized = type.toLowerCase();
  return labels[normalized] ?? `${normalized.charAt(0).toLocaleUpperCase('ru-RU')}${normalized.slice(1)}`;
}
