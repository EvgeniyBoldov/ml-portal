import type { AgentData, OrchestratorData, PhaseData, PlannerData, ToolData, TraceEntity } from './entityTypes';

export type TraceSnapshotInspectorKind = 'entity' | 'call' | 'phase' | 'error' | 'unknown';

function shortName(value: string): string {
  const clean = value.trim();
  if (!clean) return clean;
  if (clean.length <= 36) return clean;
  return `${clean.slice(0, 33)}...`;
}

function compactSlug(slug: string): string {
  const clean = slug.trim();
  if (!clean) return clean;
  const parts = clean.split(/[./:]/).filter(Boolean);
  if (parts.length === 0) return shortName(clean);
  if (parts.length === 1) return shortName(parts[0]);
  return shortName(`${parts[parts.length - 2]}.${parts[parts.length - 1]}`);
}

export function isMemorySnapshotAgent(entity: TraceEntity): boolean {
  if (entity.kind !== 'agent' || entity.data.kind !== 'agent') return false;
  const slug = String(entity.data.slug ?? '').toLowerCase();
  return slug === 'facts' || slug === 'fact_extractor' || slug === 'conversation' || slug === 'summary_compactor';
}

export function getTraceEntityKindLabel(entity: TraceEntity): string {
  if (isMemorySnapshotAgent(entity)) return 'Оркестратор';
  if (entity.kind === 'run') return 'Run';
  if (entity.kind === 'phase') return 'Фаза';
  if (entity.kind === 'orchestrator') return 'Оркестратор';
  if (entity.kind === 'planner') return 'Шаг';
  if (entity.kind === 'agent') return 'Агент';
  if (entity.kind === 'llm') return 'LLM';
  if (entity.kind === 'tool') return 'Tool';
  if (entity.kind === 'error') return 'Ошибка';
  return 'Прочее';
}

export function getTraceEntityTitle(entity: TraceEntity): string {
  if (entity.kind === 'run' && entity.data.kind === 'run') {
    return shortName(entity.data.userRequest?.trim() || 'Run');
  }
  if (entity.kind === 'phase' && entity.data.kind === 'phase') {
    const phase = entity.data as PhaseData;
    return phase.phaseRole === 'memory' ? 'Память' : 'Подготовка ответа';
  }
  if (entity.kind === 'orchestrator' && entity.data.kind === 'orchestrator') {
    const orchestrator = entity.data as OrchestratorData;
    const role = String(orchestrator.role ?? '').toLowerCase();
    if (role === 'planner') return 'Планировщик';
    if (role === 'synthesizer') return 'Синтез';
    if (role === 'memory') return 'Память';
    return shortName(orchestrator.slug || entity.title);
  }
  if (entity.kind === 'planner' && entity.data.kind === 'planner') {
    const planner = entity.data as PlannerData;
    if (planner.stepKind === 'iteration') return shortName(entity.title);
    if (planner.stepKind === 'call_agent') return 'Выбор агента';
    if (planner.stepKind === 'final' || planner.stepKind === 'direct_answer') return 'Финальный ответ';
    if (planner.stepKind === 'ask_user' || planner.stepKind === 'clarify') return 'Уточнение';
    if (planner.stepKind === 'abort') return 'Прерывание';
    return 'Шаг';
  }
  if (entity.kind === 'agent' && entity.data.kind === 'agent') {
    const agent = entity.data as AgentData;
    const slug = String(agent.slug ?? '').toLowerCase();
    if (slug === 'facts' || slug === 'fact_extractor') return 'Факты';
    if (slug === 'conversation' || slug === 'summary_compactor') return 'Сводка';
    return compactSlug(agent.slug || entity.title);
  }
  if (entity.kind === 'llm') return 'LLM';
  if (entity.kind === 'tool' && entity.data.kind === 'tool') {
    const tool = entity.data as ToolData;
    return compactSlug(tool.toolSlug || entity.title);
  }
  if (entity.kind === 'error' && entity.data.kind === 'error') {
    return shortName(entity.data.userMessage || entity.title);
  }
  return shortName(entity.title);
}

export function getTraceSnapshotInspectorKind(entity: TraceEntity): TraceSnapshotInspectorKind {
  if (entity.kind === 'phase') return 'phase';
  if (entity.kind === 'llm' || entity.kind === 'tool') return 'call';
  if (entity.kind === 'error') return 'error';
  if (entity.kind === 'run' || entity.kind === 'agent' || entity.kind === 'orchestrator' || entity.kind === 'planner') {
    return 'entity';
  }
  return 'unknown';
}
