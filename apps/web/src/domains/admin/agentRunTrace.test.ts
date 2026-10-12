import { describe, expect, it } from 'vitest';
import type { AgentRunDetail } from '@/shared/api/admin';
import { replayRuntimeJournal } from '@/domains/sandbox/traceState';
import {
  projectTraceStages,
  traceElapsedMs,
} from '@/domains/sandbox/traceProjection';
import { agentRunTraceEvents, normalizeAgentRunEvents } from './agentRunTrace';

function runFixture(
  inputs: Record<string, unknown> = {
    description: 'Перенести систему без простоя',
  }
): AgentRunDetail {
  return {
    agent_execution_id: 'agent-1',
    run_id: 'run-1',
    agent_slug: 'test.naruto',
    events: [
      {
        id: 'start',
        run_id: 'run-1',
        sequence: 2,
        event_type: 'agent_start',
        occurred_at: '2026-10-12T20:40:05.139Z',
        entity_type: 'agent_execution',
        entity_id: 'agent-1',
        parent_entity_type: 'run',
        parent_entity_id: 'run-1',
        payload: {
          task_id: 'task-1',
          task_title: 'Shadow invocation',
          agent_slug: 'test.naruto',
        },
      },
      {
        id: 'snapshot',
        run_id: 'run-1',
        sequence: 8,
        event_type: 'status',
        occurred_at: '2026-10-12T20:40:05.163Z',
        entity_type: 'agent_execution',
        entity_id: 'agent-1',
        parent_entity_type: 'run',
        parent_entity_id: 'run-1',
        payload: {
          stage: 'agent_context_snapshot',
          context_snapshot: {
            inputs: {
              task_id: 'task-1',
              goal: 'Classify supplied description',
              intent: 'Shadow invocation',
              instructions: 'Return a JSON classification',
              inputs,
            },
          },
        },
      },
      {
        id: 'end',
        run_id: 'run-1',
        sequence: 22,
        event_type: 'agent_end',
        occurred_at: '2026-10-12T20:40:08.873Z',
        entity_type: 'agent_execution',
        entity_id: 'agent-1',
        parent_entity_type: 'run',
        parent_entity_id: 'run-1',
        payload: { status: 'completed', agent_slug: 'test.naruto' },
      },
    ],
  };
}

describe('agent task inspection', () => {
  it.each(['agent-run', 'sandbox'])(
    'reads saved task inputs in the %s inspector',
    view => {
      const run = runFixture();
      const events = normalizeAgentRunEvents(run.events);
      const journal =
        view === 'sandbox'
          ? [
              {
                ...events[0],
                id: 'iteration',
                sequence: 0,
                event_type: 'planner_iteration_start',
                entity_type: 'planner_iteration',
                entity_id: 'iteration-1',
                parent_entity_type: null,
                parent_entity_id: null,
                payload: { iteration_number: 1 },
              },
              {
                ...events[0],
                id: 'step',
                sequence: 1,
                event_type: 'step_start',
                entity_type: 'step',
                entity_id: 'step-1',
                parent_entity_type: 'planner_iteration',
                parent_entity_id: 'iteration-1',
                payload: {},
              },
              ...events.map(event => ({
                ...event,
                parent_entity_type: 'step',
                parent_entity_id: 'step-1',
              })),
            ]
          : agentRunTraceEvents(run);
      const stage = projectTraceStages(replayRuntimeJournal(journal))[0];
      expect(stage.executorRuns[0].taskPresentation).toMatchObject({
        taskId: 'task-1',
        objective: 'Classify supplied description',
        intent: 'Shadow invocation',
        instructions: 'Return a JSON classification',
        inputs: { description: 'Перенести систему без простоя' },
        status: 'Готово',
      });
      expect(stage.steps[0].taskPresentation?.inputs).toEqual({
        description: 'Перенести систему без простоя',
      });
    }
  );

  it('preserves an explicitly empty input object', () => {
    const stage = projectTraceStages(
      replayRuntimeJournal(agentRunTraceEvents(runFixture({})))
    )[0];
    expect(stage.executorRuns[0].taskPresentation?.inputs).toEqual({});
  });
});

describe('agent journal duration', () => {
  it('stops duration at agent_end when the journal contains only the agent subgraph', () => {
    const state = replayRuntimeJournal(
      normalizeAgentRunEvents(runFixture().events)
    );
    expect(traceElapsedMs(state, Date.parse('2026-10-12T20:41:34.291Z'))).toBe(
      3734
    );
  });

  it('keeps the run clock active after an agent ends in an ongoing sandbox run', () => {
    const run = runFixture();
    const events = normalizeAgentRunEvents(run.events);
    const start = {
      ...events[0],
      id: 'run-start',
      sequence: 1,
      event_type: 'run_start',
      entity_type: 'run',
      entity_id: 'run-1',
      parent_entity_type: null,
      parent_entity_id: null,
    };
    expect(
      traceElapsedMs(
        replayRuntimeJournal([start, ...events]),
        Date.parse('2026-10-12T20:41:34.291Z')
      )
    ).toBe(89152);
  });
});

function withFinal(content: unknown): AgentRunDetail {
  const run = runFixture();
  run.events.splice(2, 0, {
    ...run.events[1],
    id: 'final',
    sequence: 20,
    event_type: 'final',
    occurred_at: '2026-10-12T20:40:08.867Z',
    payload: { content, sources: [] },
  });
  return run;
}

describe('agent result inspection', () => {
  it('shows validated structured_response from final when agent_end only has lifecycle metadata', () => {
    const run = withFinal(
      '{"completion":"fulfilled","structured_response":{"class":"сложный"}}'
    );
    const stage = projectTraceStages(
      replayRuntimeJournal(agentRunTraceEvents(run))
    )[0];
    expect(stage.executorRuns[0].result).toMatchObject({
      status: 'completed',
      output: { class: 'сложный' },
    });
    expect(stage.steps[0].executorRuns[0].result.output).toEqual({
      class: 'сложный',
    });
  });

  it.each([{}, [], false, 0, null])(
    'preserves the declared JSON result %j',
    output => {
      const run = withFinal(
        JSON.stringify({ completion: 'fulfilled', structured_response: output })
      );
      const stage = projectTraceStages(
        replayRuntimeJournal(agentRunTraceEvents(run))
      )[0];
      expect(stage.executorRuns[0].result.output).toEqual(output);
    }
  );

  it('shows answer when the completion declaration has a text result', () => {
    const stage = projectTraceStages(
      replayRuntimeJournal(
        agentRunTraceEvents(
          withFinal('{"completion":"fulfilled","answer":"Готово"}')
        )
      )
    )[0];
    expect(stage.executorRuns[0].result.output).toBe('Готово');
  });

  it('preserves the failed lifecycle status after output validation rejected the response', () => {
    const run = withFinal(
      '{"completion":"fulfilled","structured_response":"invalid API result"}'
    );
    run.events.at(-1)!.payload.status = 'failed';
    const stage = projectTraceStages(
      replayRuntimeJournal(agentRunTraceEvents(run))
    )[0];
    expect(stage.executorRuns[0].result.status).toBe('failed');
  });

  it('does not use a raw llm_response as the validated final result', () => {
    const run = withFinal(
      '{"completion":"fulfilled","structured_response":{"class":"сложный"}}'
    );
    run.events[2].event_type = 'llm_response';
    const stage = projectTraceStages(
      replayRuntimeJournal(agentRunTraceEvents(run))
    )[0];
    expect(stage.executorRuns[0].result.output).toBeUndefined();
  });
});
