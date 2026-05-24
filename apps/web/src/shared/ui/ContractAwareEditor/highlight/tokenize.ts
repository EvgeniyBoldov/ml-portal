export type MentionRange = {
  start: number;
  end: number;
};

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function findFieldMentions(text: string, fieldName: string): MentionRange[] {
  const source = (text ?? '').toString();
  const needle = (fieldName ?? '').trim();
  if (!source || !needle) return [];

  const escaped = escapeRegExp(needle);
  const pattern = new RegExp(`(^|[^a-zA-Z0-9_])(${escaped})(?=$|[^a-zA-Z0-9_])`, 'gi');
  const ranges: MentionRange[] = [];

  let match: RegExpExecArray | null = pattern.exec(source);
  while (match) {
    const prefix = match[1] ?? '';
    const value = match[2] ?? '';
    const start = match.index + prefix.length;
    const end = start + value.length;
    ranges.push({ start, end });
    match = pattern.exec(source);
  }

  return ranges;
}

export function buildHighlightedHtml(text: string, ranges: MentionRange[], fieldName?: string | null): string {
  const source = (text ?? '').toString();
  if (!source) return '';
  if (!ranges.length) return escapeHtml(source);

  let cursor = 0;
  let out = '';
  for (const range of ranges) {
    if (range.start < cursor) continue;
    out += escapeHtml(source.slice(cursor, range.start));
    const attr = fieldName ? ` data-field="${escapeHtml(fieldName)}"` : '';
    out += `<mark${attr}>${escapeHtml(source.slice(range.start, range.end))}</mark>`;
    cursor = range.end;
  }
  out += escapeHtml(source.slice(cursor));
  return out;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
