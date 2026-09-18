import type { AgentRunDetail } from '@/shared/api/admin';
import type { RuntimeJournalEvent } from '@/domains/sandbox/types';

/**
 * The reusable sandbox trace starts at a planner iteration. An agent-run API
 * intentionally returns only the agent subgraph, so its parent step and
 * iteration are outside the payload. Add display-only ancestors here instead
 * of changing the shared trace components or polluting the persisted journal.
 */
export function agentRunTraceEvents(run: AgentRunDetail): RuntimeJournalEvent[] {
  const events = run.events.map((event) => ({ ...event })) as RuntimeJournalEvent[];
  const agentStart = events.find((event) => event.event_type === 'agent_start' && event.entity_type === 'agent_execution');
  if (!agentStart?.entity_id) return events;
  const stepId = agentStart.parent_entity_id || `agent-run-step-${run.agent_execution_id}`;
  const iterationId = `agent-run-iteration-${run.agent_execution_id}`;
  const occurredAt = agentStart.occurred_at;
  const taskTitle = typeof agentStart.payload.task_title === 'string' ? agentStart.payload.task_title : 'Выполнение агента';
  const synthetic: RuntimeJournalEvent[] = [
    {
      id: `synthetic-iteration-${run.agent_execution_id}`, run_id: run.run_id, sequence: -2,
      event_type: 'planner_iteration_start', occurred_at: occurredAt,
      entity_type: 'planner_iteration', entity_id: iterationId, parent_entity_type: null, parent_entity_id: null,
      caused_by_event_id: null, duration_ms: null,
      payload: { entity_type: 'planner_iteration', entity_id: iterationId, iteration_number: 1, iteration_type: 'execution' },
    },
    {
      id: `synthetic-step-${run.agent_execution_id}`, run_id: run.run_id, sequence: -1,
      event_type: 'step_start', occurred_at: occurredAt,
      entity_type: 'step', entity_id: stepId, parent_entity_type: 'planner_iteration', parent_entity_id: iterationId,
      caused_by_event_id: null, duration_ms: null,
      payload: { entity_type: 'step', entity_id: stepId, parent_entity_type: 'planner_iteration', parent_entity_id: iterationId, title: taskTitle, objective: taskTitle },
    },
  ];
  return [...synthetic, ...events.map((event) => (
    event.entity_type === 'agent_execution' && event.entity_id === agentStart.entity_id
      ? { ...event, parent_entity_type: 'step', parent_entity_id: stepId, payload: { ...event.payload, parent_entity_type: 'step', parent_entity_id: stepId } }
      : event
  ))];
}
