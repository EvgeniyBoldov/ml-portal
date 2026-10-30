export interface TemplateDescriptionSection {
  heading: 'Поля' | 'Таблицы';
  items: string[];
}

export interface ParsedTemplateDescription {
  introduction: string;
  sections: TemplateDescriptionSection[];
  fallback: string;
}

const STAGE_DESCRIPTIONS: Record<string, string> = {
  uploaded: 'Получение файла шаблона и его основных параметров.',
  schema: 'Определение полей, таблиц и структуры шаблона.',
  description: 'Подготовка текстового описания шаблона.',
  approval: 'Согласование структуры и описания шаблона.',
  vectorization: 'Подготовка представления шаблона для поиска.',
  indexing: 'Добавление подготовленных данных в поисковый индекс.',
  ready: 'Итоговое состояние шаблона и сведения о готовности.',
};

const STATUS_LABELS: Record<string, string> = {
  approved: 'Утверждён',
  approval_required: 'Ожидает согласования',
  archived: 'В архиве',
  cancelled: 'Остановлено',
  completed: 'Завершено',
  error: 'Ошибка',
  failed: 'Ошибка',
  pending: 'В ожидании',
  processing: 'Выполняется',
  queued: 'В очереди',
  ready: 'Готов',
  uploaded: 'Загружен',
};

const FORMAT_LABELS: Record<string, string> = {
  csv: 'CSV',
  excel: 'Excel',
  xls: 'Excel',
  xlsx: 'Excel',
  json: 'JSON',
};

export function getTemplateStageDescription(stageKey: string): string {
  return STAGE_DESCRIPTIONS[stageKey] ?? 'Сведения о текущем этапе обработки шаблона.';
}

export function formatTemplateStatus(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return 'Не указан';
  const normalized = value.trim().toLowerCase();
  if (STATUS_LABELS[normalized]) return STATUS_LABELS[normalized];
  const readable = normalized.replace(/[_-]+/g, ' ');
  return readable.charAt(0).toLocaleUpperCase('ru-RU') + readable.slice(1);
}

export function formatTemplateFormat(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) return null;
  const normalized = value.trim().toLowerCase();
  return FORMAT_LABELS[normalized] ?? value.trim();
}

export function truncateTemplateIdentifier(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

export function parseTemplateDescription(description: string): ParsedTemplateDescription {
  const headingPattern = /(?:^|\s)(Поля|Таблицы):\s*/gi;
  const matches = Array.from(description.matchAll(headingPattern));
  if (matches.length === 0) {
    return { introduction: '', sections: [], fallback: description };
  }

  const first = matches[0];
  const introduction = description.slice(0, first.index ?? 0).trim();
  const sections = matches.map((match, index) => {
    const heading = match[1] as TemplateDescriptionSection['heading'];
    const contentStart = (match.index ?? 0) + match[0].length;
    const next = matches[index + 1];
    const contentEnd = next?.index ?? description.length;
    const content = description.slice(contentStart, contentEnd).trim();
    const items = content.split(/\s*•\s*/).map((item) => item.trim()).filter(Boolean);
    return { heading, items };
  });

  return { introduction, sections, fallback: '' };
}

