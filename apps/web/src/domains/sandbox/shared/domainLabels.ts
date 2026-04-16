const DOMAIN_LABELS: Record<string, string> = {
  llm: 'LLM',
  mcp: 'MCP',
  'collection.document': 'Коллекции · документы',
  'collection.table': 'Коллекции · таблицы',
  rag: 'RAG',
  jira: 'Jira',
  netbox: 'NetBox',
  dcbox: 'DCBox',
};

export function formatSandboxDomainLabel(domain: string): string {
  return DOMAIN_LABELS[domain] ?? domain.replace(/\./g, ' · ');
}

export function formatSandboxDomainTone(domain: string): 'neutral' | 'info' | 'success' | 'warn' | 'danger' {
  if (domain === 'mcp') return 'info';
  if (domain === 'llm') return 'neutral';
  if (domain.startsWith('collection.')) return 'success';
  if (domain === 'rag') return 'warn';
  if (domain === 'jira' || domain === 'netbox' || domain === 'dcbox') return 'info';
  return 'neutral';
}
