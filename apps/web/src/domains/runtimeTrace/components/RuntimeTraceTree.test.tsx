import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RuntimeTraceTree } from './RuntimeTraceTree';
import type { SemanticEvent } from '../types';

function ev(id: string, raw_type: string, raw: Record<string, unknown>, category = 'system'): SemanticEvent {
  return {
    id,
    raw_type,
    category: category as SemanticEvent['category'],
    title: raw_type,
    summary: '',
    status: 'info',
    phase: 'system',
    iteration: 0,
    started_at: new Date().toISOString(),
    duration_ms: 10,
    refs: {},
    raw: { id, raw_type, raw },
  };
}

describe('RuntimeTraceTree', () => {
  it('renders synthetic phases and key nodes for lifecycle stream', () => {
    const runId = 'run-1';
    const orchId = `${runId}:orchestrator`;
    const iterId = `${runId}:planner:1`;
    const agentId = `${runId}:agent:viewer:1`;
    const synthId = `${runId}:synthesis:1`;
    const memId = `${runId}:memory`;

    const events: SemanticEvent[] = [
      ev('1', 'run_start', { entity_id: runId, entity_type: 'run' }),
      ev('2', 'orchestrator_start', { entity_id: orchId, entity_type: 'orchestrator', parent_entity_id: runId, parent_entity_type: 'run', role: 'planner' }),
      ev('3', 'planner_iteration_start', { entity_id: iterId, entity_type: 'planner_iteration', parent_entity_id: orchId, parent_entity_type: 'orchestrator', iteration: 1 }),
      ev('4', 'agent_start', { entity_id: agentId, entity_type: 'agent_run', parent_entity_id: iterId, parent_entity_type: 'planner_iteration', agent_slug: 'viewer' }),
      ev('5', 'agent_end', { entity_id: agentId, entity_type: 'agent_run', parent_entity_id: iterId, parent_entity_type: 'planner_iteration', agent_slug: 'viewer', status: 'completed' }),
      ev('6', 'planner_iteration_end', { entity_id: iterId, entity_type: 'planner_iteration', parent_entity_id: orchId, iteration: 1, status: 'completed' }),
      ev('7', 'orchestrator_end', { entity_id: orchId, entity_type: 'orchestrator', parent_entity_id: runId, status: 'completed' }),
      ev('8', 'synthesis_start', { entity_id: synthId, entity_type: 'synthesis_run', parent_entity_id: runId, parent_entity_type: 'run' }),
      ev('9', 'synthesis_end', { entity_id: synthId, entity_type: 'synthesis_run', parent_entity_id: runId, status: 'completed' }),
      ev('10', 'orchestrator_start', { entity_id: memId, entity_type: 'orchestrator', parent_entity_id: runId, parent_entity_type: 'run', role: 'memory' }),
      ev('11', 'orchestrator_end', { entity_id: memId, entity_type: 'orchestrator', parent_entity_id: runId, status: 'completed' }),
      ev('12', 'run_end', { entity_id: runId, entity_type: 'run', status: 'completed' }),
    ];

    render(<RuntimeTraceTree events={events} />);
    expect(screen.getByText('Подготовка ответа')).toBeInTheDocument();
    expect(screen.getByText('Мемори')).toBeInTheDocument();
    expect(screen.getByText('Planner')).toBeInTheDocument();
    expect(screen.getByText('Синтезер')).toBeInTheDocument();
  });
});
