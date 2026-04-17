export function formatSchemaPropertyType(property: unknown): string {
  if (!property || typeof property !== 'object') return 'unknown';
  const entry = property as Record<string, unknown>;
  const jsonType = entry.type;
  const jsonFormat = entry.format;
  if (typeof jsonType === 'string' && typeof jsonFormat === 'string') {
    return `${jsonType} (${jsonFormat})`;
  }
  if (typeof jsonType === 'string') return jsonType;
  return 'unknown';
}

export function renderSchemaLines(tableSchema: Record<string, unknown> | undefined): string[] {
  const properties = (tableSchema?.properties ?? {}) as Record<string, unknown>;
  return Object.entries(properties).map(([name, spec]) => `${name}: ${formatSchemaPropertyType(spec)}`);
}
