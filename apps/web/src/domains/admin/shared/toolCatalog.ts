import type {
  DiscoveredToolListItem,
  ToolResultDelivery,
  ToolRisk,
  ToolSourceType,
} from '@/shared/api/discoveredTools';

export const TOOLS_PATH = '/admin/tools';
export const BUILTIN_PROVIDER = 'builtin';

export const sourceLabels: Record<ToolSourceType, string> = {
  system: 'Системные',
  table: 'Таблицы',
  document: 'Документы',
  template: 'Шаблоны',
  sql: 'SQL',
  api: 'API',
};

export const deliveryLabels: Record<ToolResultDelivery, string> = {
  direct: 'В контекст',
  store: 'В набор данных',
};

const riskLabels = {
  safe: { label: 'Безопасный', tone: 'success', sortOrder: 0 },
  risky: { label: 'Рискованный', tone: 'danger', sortOrder: 3 },
  unclassified: { label: 'Требует классификации', tone: 'warn', sortOrder: 2 },
  inherited: { label: 'По умолчанию', tone: 'neutral', sortOrder: 1 },
} as const;

export const riskOptions = Object.entries(riskLabels).map(
  ([value, { label }]) => ({
    value,
    label,
  })
);

export function riskKey(tool: DiscoveredToolListItem) {
  return (
    tool.risk_level ?? (tool.source === 'mcp' ? 'unclassified' : 'inherited')
  );
}

export function toolRisk(tool: DiscoveredToolListItem) {
  return riskLabels[riskKey(tool)];
}

export const riskEditOptions: { value: ToolRisk; label: string }[] = [
  { value: 'safe', label: riskLabels.safe.label },
  { value: 'risky', label: riskLabels.risky.label },
];

export function providerName(tool: DiscoveredToolListItem) {
  return tool.connector_name ?? tool.connector_slug ?? 'Встроенный';
}

export function providerKind(tool: DiscoveredToolListItem) {
  if (tool.source === 'mcp') return 'MCP';
  return tool.source_types?.includes('system') ? 'Системный' : 'Локальный';
}

export function toolSourceLabels(tool: DiscoveredToolListItem) {
  return (tool.source_types ?? []).map(type => sourceLabels[type]);
}

export function matchesTool(tool: DiscoveredToolListItem, query: string) {
  const searchable = [
    tool.name,
    tool.slug,
    tool.description,
    tool.connector_slug,
    providerName(tool),
    providerKind(tool),
    ...toolSourceLabels(tool),
  ]
    .join(' ')
    .toLowerCase();

  return query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .every(word => searchable.includes(word));
}
