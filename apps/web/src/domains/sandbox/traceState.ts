import type { RuntimeJournalEvent } from './types';
import { llmResponseStatus, toolResult } from './callInspection';

export type { RuntimeJournalEvent } from './types';

export type TraceEntity = {
  key: string;
  type: string;
  id: string;
  parentKey: string | null;
  childKeys: string[];
  eventIds: string[];
  status: string;
  snapshotsByKind: Record<string, string>;
};

export type SandboxTraceState = {
  runId: string | null;
  rootEntityKey: string | null;
  eventsById: Record<string, RuntimeJournalEvent>;
  eventIdsBySequence: string[];
  entitiesByKey: Record<string, TraceEntity>;
  nextSequence: number | null;
  pendingBySequence: Record<number, RuntimeJournalEvent>;
  protocolError: string | null;
};

export const emptySandboxTrace = (): SandboxTraceState => ({
  runId: null, rootEntityKey: null, eventsById: {}, eventIdsBySequence: [],
  entitiesByKey: {}, nextSequence: 1, pendingBySequence: {}, protocolError: null,
});

const keyOf = (type: string, id: string): string => `${type}:${id}`;
const stringField = (value: unknown): string => typeof value === 'string' ? value : '';
const CREATE_EVENT_TYPES = new Set([
  'llm_request',
  'tool_call',
]);

const isCreate = (type: string): boolean => (
  type.endsWith('_start') || type.endsWith('_started') || CREATE_EVENT_TYPES.has(type)
);
const isEnd = (type: string): boolean => type.endsWith('_end') || type.endsWith('_finished') || type.endsWith('_completed') || type.endsWith('_failed');
const isSnapshot = (type: string): boolean => type.endsWith('_snapshot') || type === 'rbac_snapshot' || type === 'limit_snapshot';

function insertEventIdBySequence(
  eventIds: string[],
  eventsById: Record<string, RuntimeJournalEvent>,
  event: RuntimeJournalEvent,
): string[] {
  return [...eventIds, event.id].sort((left, right) => {
    const leftSequence = left === event.id ? event.sequence : eventsById[left]?.sequence ?? 0;
    const rightSequence = right === event.id ? event.sequence : eventsById[right]?.sequence ?? 0;
    return leftSequence - rightSequence;
  });
}

function terminalStatus(event: RuntimeJournalEvent): string | undefined {
  if (event.entity_type === 'task' && event.event_type === 'task_unfulfillable') return 'unfulfillable';
  if (event.entity_type === 'task' && event.event_type === 'task_blocked') return 'blocked';
  if (event.entity_type === 'task' && event.event_type === 'task_completed') return 'completed';
  if (event.entity_type === 'task' && event.event_type === 'task_failed') return 'failed';
  if ((event.entity_type === 'task' || event.entity_type === 'checkpoint') && stringField(event.payload.status)) {
    return stringField(event.payload.status) || undefined;
  }
  if (event.event_type === 'protocol_retry') return 'waiting_retry';
  if (event.event_type === 'llm_request' || event.event_type === 'tool_call') return 'running';
  if (event.event_type === 'tool_result') {
    const success = toolResult(event.payload).success;
    return success === true ? 'completed' : success === false ? 'failed' : 'unknown';
  }
  if (event.event_type === 'llm_response') {
    const declared = stringField(event.payload.status).toLowerCase();
    if (declared === 'running' || declared === 'waiting_retry' || declared === 'failed' || declared === 'completed') {
      return declared;
    }
    if (llmResponseStatus(event.payload) === 'error') {
      return event.payload.retryable === true ? 'waiting_retry' : 'failed';
    }
    return 'completed';
  }
  if (event.event_type === 'question_answer') return 'completed';
  if (event.event_type === 'error') return 'error';
  if (event.event_type.endsWith('_failed')) return 'failed';
  return isEnd(event.event_type) ? String(event.payload.status ?? 'completed') : undefined;
}

function applyOrderedJournalEvent(state: SandboxTraceState, event: RuntimeJournalEvent): SandboxTraceState {
  const entityType = event.entity_type ?? stringField(event.payload.entity_type);
  const entityId = event.entity_id ?? stringField(event.payload.entity_id);
  if (!entityType || !entityId) {
    return {
      ...state, runId: state.runId ?? event.run_id,
      eventsById: { ...state.eventsById, [event.id]: event },
      eventIdsBySequence: insertEventIdBySequence(state.eventIdsBySequence, state.eventsById, event),
      nextSequence: Math.max(state.nextSequence ?? 1, event.sequence + 1),
    };
  }
  const entityKey = keyOf(entityType, entityId);
  const parentType = event.parent_entity_type ?? stringField(event.payload.parent_entity_type);
  const parentId = event.parent_entity_id ?? stringField(event.payload.parent_entity_id);
  const parentKey = parentType && parentId ? keyOf(parentType, parentId) : null;
  const existing = state.entitiesByKey[entityKey];
  // Journal rows are authoritative and can be replayed after a process
  // restart.  Older runs may contain an update before the corresponding
  // start row (or a planner call whose executor start was not emitted). Keep
  // the event and materialize a placeholder instead of dropping the rest of
  // the sequence behind a protocol error.
  const parentPlaceholder = parentKey && !state.entitiesByKey[parentKey]
    ? {
        key: parentKey,
        type: parentType,
        id: parentId,
        parentKey: null,
        childKeys: [],
        eventIds: [],
        status: 'running',
        snapshotsByKind: {},
      } satisfies TraceEntity
    : null;
  const entity: TraceEntity = existing ?? {
    key: entityKey, type: entityType, id: entityId, parentKey, childKeys: [], eventIds: [], status: 'running', snapshotsByKind: {},
  };
  const nextEntity: TraceEntity = {
    ...entity,
    parentKey: entity.parentKey ?? parentKey,
    eventIds: insertEventIdBySequence(entity.eventIds, state.eventsById, event),
    status: terminalStatus(event) ?? entity.status,
    snapshotsByKind: isSnapshot(event.event_type)
      ? { ...entity.snapshotsByKind, [event.event_type]: event.id }
      : entity.snapshotsByKind,
  };
  const entitiesByKey: Record<string, TraceEntity> = {
    ...state.entitiesByKey,
    ...(parentPlaceholder ? { [parentKey!]: parentPlaceholder } : {}),
    [entityKey]: nextEntity,
  };
  if (parentKey) {
    const parent = entitiesByKey[parentKey];
    entitiesByKey[parentKey] = parent.childKeys.includes(entityKey)
      ? parent
      : { ...parent, childKeys: [...parent.childKeys, entityKey] };
  }
  return {
    runId: state.runId ?? event.run_id,
    rootEntityKey: entityType === 'run' ? entityKey : state.rootEntityKey,
    eventsById: { ...state.eventsById, [event.id]: event },
    eventIdsBySequence: insertEventIdBySequence(state.eventIdsBySequence, state.eventsById, event),
    entitiesByKey,
    nextSequence: Math.max(state.nextSequence ?? 1, event.sequence + 1),
    pendingBySequence: state.pendingBySequence,
    protocolError: null,
  };
}

export function applyRuntimeJournalEvent(state: SandboxTraceState, event: RuntimeJournalEvent): SandboxTraceState {
  if (state.eventsById[event.id]) return state;
  // Redis Pub/Sub is live-only: frames can arrive out of order or one can be
  // lost before the terminal DB replay. Entity placeholders make each journal
  // row independently applicable, so never let one missing sequence freeze
  // the rest of the visible trace.
  return applyOrderedJournalEvent({ ...state, pendingBySequence: {} }, event);
}

export function replayRuntimeJournal(events: RuntimeJournalEvent[]): SandboxTraceState {
  return [...events].sort((a, b) => a.sequence - b.sequence).reduce(applyRuntimeJournalEvent, emptySandboxTrace());
}
