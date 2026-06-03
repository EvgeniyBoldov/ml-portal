import { describe, expect, it } from 'vitest';
import type { TraceEntity } from './entityTypes';
import {
  getTraceEntityKindLabel,
  getTraceEntityTitle,
  getTraceSnapshotInspectorKind,
} from './tracePresentation';

function makeEntity(overrides: Partial<TraceEntity>): TraceEntity {
  return {
    id: overrides.id ?? 'entity-1',
    kind: overrides.kind ?? 'unknown',
    parentId: overrides.parentId ?? null,
    depth: overrides.depth ?? 0,
    children: overrides.children ?? [],
    title: overrides.title ?? 'Entity',
    status: overrides.status ?? 'info',
    sourceEventIds: overrides.sourceEventIds ?? [],
    data: overrides.data ?? { kind: 'unknown', rawType: 'unknown', raw: {}, hint: '' },
  };
}

describe('tracePresentation', () => {
  it('maps memory snapshot agents to orchestrator presentation', () => {
    const entity = makeEntity({
      kind: 'agent',
      title: 'Fact Extractor',
      data: { kind: 'agent', slug: 'fact_extractor', prompt: { isBriefMode: false } },
    });

    expect(getTraceEntityKindLabel(entity)).toBe('Оркестратор');
    expect(getTraceEntityTitle(entity)).toBe('Факты');
    expect(getTraceSnapshotInspectorKind(entity)).toBe('entity');
  });

  it('maps llm entities to call inspection', () => {
    const entity = makeEntity({
      kind: 'llm',
      data: { kind: 'llm' },
    });

    expect(getTraceEntityKindLabel(entity)).toBe('LLM');
    expect(getTraceEntityTitle(entity)).toBe('LLM');
    expect(getTraceSnapshotInspectorKind(entity)).toBe('call');
  });

  it('keeps synthetic phases as phase inspection', () => {
    const entity = makeEntity({
      kind: 'phase',
      title: 'Memory Phase',
      data: { kind: 'phase', phaseRole: 'memory' },
    });

    expect(getTraceEntityKindLabel(entity)).toBe('Фаза');
    expect(getTraceEntityTitle(entity)).toBe('Память');
    expect(getTraceSnapshotInspectorKind(entity)).toBe('phase');
  });

  it('maps interaction entities to entity inspection', () => {
    const entity = makeEntity({
      kind: 'interaction',
      title: 'Question answered',
      data: { kind: 'interaction', interactionKind: 'clarify', question: 'Q', answer: 'A' },
    });

    expect(getTraceEntityKindLabel(entity)).toBe('Диалог');
    expect(getTraceEntityTitle(entity)).toBe('Уточнение');
    expect(getTraceSnapshotInspectorKind(entity)).toBe('entity');
  });
});
