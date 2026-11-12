import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { resolveTraceInspectionTarget } from '../../traceProjection';
import { replayRuntimeJournal, type RuntimeJournalEvent } from '../../traceState';
import type { TraceToolResult } from '../../traceProjection';
import { ToolResponse } from './CallViews';
import { ToolDataViewer } from './ToolDataViewer';

const event = (sequence: number, eventType: string, payload: Record<string, unknown>): RuntimeJournalEvent => ({
  id: `event-${sequence}`,
  run_id: 'run-1',
  sequence,
  event_type: eventType,
  occurred_at: '2026-08-21T08:55:00.000Z',
  entity_type: typeof payload.entity_type === 'string' ? payload.entity_type : null,
  entity_id: typeof payload.entity_id === 'string' ? payload.entity_id : null,
  parent_entity_type: typeof payload.parent_entity_type === 'string' ? payload.parent_entity_type : null,
  parent_entity_id: typeof payload.parent_entity_id === 'string' ? payload.parent_entity_id : null,
  caused_by_event_id: null,
  duration_ms: null,
  payload,
});

describe('ToolDataViewer', () => {
  it('shows a bounded record preview, counts, and independent completeness facts', () => {
    const result: TraceToolResult = {
      success: true,
      data: Array.from({ length: 25 }, (_, index) => ({ issue_key: `NET-${index + 1}`, title: `Issue ${index + 1}` })),
      summary: 'Получено строк: 25 из 400',
      truncated: false,
      returnedCount: 25,
      sourceTotal: 400,
      inlineComplete: true,
      sourceComplete: false,
      queryComplete: true,
    };
    render(<ToolDataViewer result={result} />);

    expect(screen.getByText('NET-1')).toBeInTheDocument();
    expect(screen.getByText('NET-20')).toBeInTheDocument();
    expect(screen.queryByText('NET-21')).not.toBeInTheDocument();
    expect(screen.getByText(/Показано 20 из 25 доступных/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Открыть доступный результат' })).toBeInTheDocument();
  });

  it('shows recovery guidance instead of an oversized direct tool body', () => {
    const recoveryResult: TraceToolResult = {
      data: undefined,
      summary: 'Результат сохранён отдельно',
      truncated: false,
      directRecovery: { resultId: 'result-1', revision: 2, reason: 'batch_context_budget' },
    };
    render(<ToolDataViewer result={recoveryResult} />);
    expect(screen.getByText('Прочитайте сохранённый результат через действие result.read.')).toBeInTheDocument();
    expect(screen.getByText('result-1')).toBeInTheDocument();
    expect(screen.queryByText('Открыть доступный результат')).not.toBeInTheDocument();
  });

  it('does not describe an unknown empty outcome as a completed operation', () => {
    const result: TraceToolResult = {
      data: undefined,
      summary: 'Результат не подтверждён',
      truncated: false,
    };
    render(<ToolDataViewer result={result} />);
    expect(screen.getByText('Подтверждённых данных нет.')).toBeInTheDocument();
  });

  it('projects a legacy stored descriptor as metadata without exposing schema internals or implying row preview', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker' }),
      event(4, 'tool_call', { entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', tool: 'result.describe', arguments: {} }),
      event(5, 'tool_result', {
        entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', success: true,
        data: {
          result_id: 'legacy-result-id', sql_ref: 'private_result_table', payload_type: 'rows', row_count: 500,
          source_total: 1200, source_complete: false, observed_schema: { secret_column: 'private' }, revision: 4, payload_chars: 15000,
        },
      }),
    ]);
    const target = resolveTraceInspectionTarget(state, 'tool_call:tool-1');
    if (target?.kind !== 'call') throw new Error('Projected tool call is missing');
    const result = target.call.responseView?.toolResult;
    if (!result) throw new Error('Projected tool result is missing');
    expect(result).toMatchObject({ storedDescriptor: true, delivery: 'stored', resultId: 'legacy-result-id', returnedCount: 500, sourceTotal: 1200 });

    render(<ToolResponse call={target.call} />);
    expect(screen.getByText('Строк в результате')).toBeInTheDocument();
    expect(screen.queryByText('private_result_table')).not.toBeInTheDocument();
    expect(screen.queryByText('observed_schema')).not.toBeInTheDocument();
    expect(screen.queryByText('secret_column')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Показать сведения о результате' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Показать сведения о результате' }));
    expect(screen.getByText('Сведения о результате')).toBeInTheDocument();
    expect(screen.queryByText('private_result_table')).not.toBeInTheDocument();
    expect(screen.queryByText('secret_column')).not.toBeInTheDocument();
  });
});
