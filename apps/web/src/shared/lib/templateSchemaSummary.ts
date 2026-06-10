export function summarizeTemplateSchema(templateSchema: Record<string, unknown> | null | undefined): string {
  if (!templateSchema || typeof templateSchema !== 'object') return '—';

  const format = String((templateSchema as { format?: unknown }).format || '').trim().toLowerCase();
  const rawSheets = (templateSchema as { sheets?: unknown }).sheets;
  const rawPlaceholders = (templateSchema as { placeholders?: unknown }).placeholders;
  const sheets: unknown[] = Array.isArray(rawSheets) ? rawSheets : [];
  const placeholders: unknown[] = Array.isArray(rawPlaceholders) ? rawPlaceholders : [];

  const sheetCount = sheets.length;
  const totalCells = sheets.reduce<number>((sum, sheet) => {
    if (!sheet || typeof sheet !== 'object') return sum;
    const cellCount = Number((sheet as { cell_count?: unknown }).cell_count ?? 0);
    return sum + (Number.isFinite(cellCount) ? cellCount : 0);
  }, 0);

  const parts: string[] = [];
  if (format) parts.push(format);
  if (sheetCount > 0) parts.push(`${sheetCount} sheet${sheetCount === 1 ? '' : 's'}`);
  if (totalCells > 0) parts.push(`${totalCells} cells`);
  if (placeholders.length > 0) parts.push(`${placeholders.length} placeholders`);

  if (parts.length > 0) {
    return parts.join(' · ');
  }

  const keys = Object.keys(templateSchema);
  if (keys.length > 0) {
    return `${keys.length} keys`;
  }

  return '—';
}
