export const TOOL_RESULT_PREVIEW_LIMIT = 20;
const MAX_COLUMNS = 6;
const MAX_VALUE_LENGTH = 300;

export type ToolDataPresentation =
  | {
      kind: 'records';
      rows: Array<Record<string, unknown>>;
      columns: string[];
      shown: number;
      available?: number;
      totalKnown: boolean;
      pageMetadata?: Record<string, unknown>;
    }
  | {
      kind: 'scalars';
      values: unknown[];
      shown: number;
      available?: number;
      totalKnown: boolean;
    }
  | { kind: 'text'; text: string }
  | {
      kind: 'record';
      entries: Array<{ key: string; label: string; value: unknown }>;
    }
  | {
      kind: 'descriptor';
      summary: string;
      counts: Array<{ label: string; value: string }>;
    }
  | { kind: 'empty' }
  | { kind: 'fallback' };

const opaqueKeys = new Set([
  'result_id',
  'sql_ref',
  'payload_ref',
  'storage_key',
  'object_key',
  'blob_id',
]);
const labelOverrides: Record<string, string> = {
  file_name: 'Файл',
  filename: 'Файл',
  name: 'Название',
  path: 'Путь',
  content_type: 'Тип файла',
  issue_key: 'Задача',
  ip: 'IP-адрес',
  status: 'Статус',
  title: 'Название',
  description: 'Описание',
  row_count: 'Строк',
  total: 'Всего',
  returned_count: 'Получено',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isOpaqueKey(key: string): boolean {
  return (
    opaqueKeys.has(key.toLowerCase()) ||
    /^(runtime|storage)_/.test(key.toLowerCase())
  );
}

export function toolDataLabel(key: string): string {
  if (labelOverrides[key.toLowerCase()])
    return labelOverrides[key.toLowerCase()];
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/^./, letter => letter.toLocaleUpperCase());
}

export function toolDataValuePreview(value: unknown): string {
  let text: string;
  try {
    text =
      typeof value === 'string'
        ? value
        : value === null || value === undefined
          ? '—'
          : typeof value === 'object'
            ? JSON.stringify(value)
            : String(value);
  } catch {
    text = '[Значение нельзя отобразить]';
  }
  const characters = Array.from(text);
  return characters.length > MAX_VALUE_LENGTH
    ? `${characters.slice(0, MAX_VALUE_LENGTH).join('')}…`
    : text;
}

function asRows(values: unknown[]): Array<Record<string, unknown>> | undefined {
  if (!values.every(isRecord)) return undefined;
  return values as Array<Record<string, unknown>>;
}

function isStoredDescriptor(
  value: Record<string, unknown>,
  options: { delivery?: string; resultId?: string }
): boolean {
  const knownMarker = ['payload_type', 'row_count', 'observed_schema'].some(
    key => key in value
  );
  const hasInlinePayload =
    Array.isArray(value.value) ||
    Array.isArray(value.rows) ||
    Array.isArray(value.sample) ||
    'text' in value;
  const stored =
    options.delivery === 'stored' &&
    Boolean(options.resultId) &&
    knownMarker &&
    !hasInlinePayload;
  const legacy =
    options.delivery === 'stored' &&
    !hasInlinePayload &&
    knownMarker &&
    ('result_id' in value ||
      'sql_ref' in value ||
      ('row_count' in value &&
        ('payload_ref' in value || 'storage_key' in value)));
  return stored || legacy;
}

export function presentToolData(
  data: unknown,
  options: {
    delivery?: string;
    resultId?: string;
    returnedCount?: number;
    sourceTotal?: number;
    truncated?: boolean;
  } = {}
): ToolDataPresentation {
  if (isRecord(data) && isRecord(data._runtime_result)) {
    const runtimeMeta = data._runtime_result;
    const payloadKey = ['data', 'rows', 'sample'].find(key => key in data);
    if (payloadKey !== undefined) {
      const nested = presentToolData(data[payloadKey], options);
      if (nested.kind === 'records') {
        const metadata = Object.fromEntries(
          Object.entries(runtimeMeta).filter(([key]) =>
            [
              'source_total',
              'returned_count',
              'row_count',
              'source_complete',
              'query_complete',
              'truncated',
            ].includes(key)
          )
        );
        return {
          ...nested,
          pageMetadata: {
            ...('pageMetadata' in nested ? nested.pageMetadata : {}),
            ...metadata,
          },
        };
      }
      return nested;
    }
    const descriptor = presentToolData(runtimeMeta, options);
    return descriptor;
  }
  if (typeof data === 'string')
    return data.length ? { kind: 'text', text: data } : { kind: 'empty' };
  if (Array.isArray(data)) {
    if (data.length === 0) return { kind: 'empty' };
    const available = data.length;
    const shown = Math.min(data.length, TOOL_RESULT_PREVIEW_LIMIT);
    const common = {
      shown,
      available,
      totalKnown:
        options.returnedCount !== undefined ||
        options.sourceTotal !== undefined,
    };
    const rows = asRows(data);
    if (rows) {
      const columns = [
        ...new Set(
          rows.flatMap(row => Object.keys(row).filter(key => !isOpaqueKey(key)))
        ),
      ].slice(0, MAX_COLUMNS);
      return {
        kind: 'records',
        rows: rows.slice(0, shown),
        columns,
        ...common,
      };
    }
    return { kind: 'scalars', values: data.slice(0, shown), ...common };
  }
  if (!isRecord(data))
    return data === null || data === undefined
      ? { kind: 'empty' }
      : {
          kind: 'scalars',
          values: [data],
          shown: 1,
          available: 1,
          totalKnown: true,
        };

  // A paged result is a deliberately recognized connector contract. Do not infer
  // collection semantics from arbitrary `data`, `items`, or `rows` properties.
  if (Array.isArray(data.value) && isRecord(data.meta)) {
    const items = data.value;
    if (items.length === 0) return { kind: 'empty' };
    const shown = Math.min(items.length, TOOL_RESULT_PREVIEW_LIMIT);
    const available = items.length;
    const rows = asRows(items);
    const metadataKeys = [
      'total',
      'count',
      'has_next',
      'complete',
      'source_complete',
    ];
    const pageMetadata = Object.fromEntries(
      Object.entries(data.meta).filter(([key]) => metadataKeys.includes(key))
    );
    const common = {
      shown,
      available,
      totalKnown:
        options.returnedCount !== undefined ||
        options.sourceTotal !== undefined,
      pageMetadata,
    };
    if (rows) {
      const columns = [
        ...new Set(
          rows.flatMap(row => Object.keys(row).filter(key => !isOpaqueKey(key)))
        ),
      ].slice(0, MAX_COLUMNS);
      return {
        kind: 'records',
        rows: rows.slice(0, shown),
        columns,
        ...common,
      };
    }
    return { kind: 'scalars', values: items.slice(0, shown), ...common };
  }

  if (isStoredDescriptor(data, options)) {
    const counts: Array<{ label: string; value: string }> = [];
    for (const [key, label] of [
      ['row_count', 'Строк в результате'],
      ['source_total', 'Всего в источнике'],
      ['returned_count', 'Доступно в ответе'],
    ]) {
      const value = data[key];
      if (typeof value === 'number')
        counts.push({
          label,
          value: new Intl.NumberFormat('ru-RU').format(value),
        });
    }
    const summary = 'Результат сохранён отдельно';
    return { kind: 'descriptor', summary, counts };
  }

  const entries = Object.entries(data)
    .filter(([key]) => !isOpaqueKey(key) && key !== '_runtime_result')
    .map(([key, value]) => ({ key, label: toolDataLabel(key), value }));
  return entries.length ? { kind: 'record', entries } : { kind: 'fallback' };
}
