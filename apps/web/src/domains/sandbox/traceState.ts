export type RuntimeJournalEvent = {
  id: string;
  run_id: string;
  sequence: number;
  event_type: string;
  occurred_at: string;
  entity_type?: string | null;
  entity_id?: string | null;
  parent_entity_type?: string | null;
  parent_entity_id?: string | null;
  caused_by_event_id?: string | null;
  duration_ms?: number | null;
  payload: Record<string, unknown>;
};

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
  protocolError: string | null;
};

export const emptySandboxTrace = (): SandboxTraceState => ({
  runId: null, rootEntityKey: null, eventsById: {}, eventIdsBySequence: [],
  entitiesByKey: {}, nextSequence: null, protocolError: null,
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
const isEnd = (type: string): boolean => type.endsWith('_end') || type.endsWith('_finished');
const isSnapshot = (type: string): boolean => type.endsWith('_snapshot') || type === 'rbac_snapshot' || type === 'limit_snapshot';

export function applyRuntimeJournalEvent(state: SandboxTraceState, event: RuntimeJournalEvent): SandboxTraceState {
  if (state.eventsById[event.id]) return state;
  if (state.nextSequence !== null && event.sequence !== state.nextSequence) {
    return { ...state, protocolError: `Expected sequence ${state.nextSequence}, received ${event.sequence}` };
  }
  const entityType = event.entity_type ?? stringField(event.payload.entity_type);
  const entityId = event.entity_id ?? stringField(event.payload.entity_id);
  if (!entityType || !entityId) {
    return {
      ...state, runId: state.runId ?? event.run_id,
      eventsById: { ...state.eventsById, [event.id]: event },
      eventIdsBySequence: [...state.eventIdsBySequence, event.id],
      nextSequence: event.sequence + 1,
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
    eventIds: [...entity.eventIds, event.id],
    status: isEnd(event.event_type) ? String(event.payload.status ?? 'completed') : entity.status,
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
    eventIdsBySequence: [...state.eventIdsBySequence, event.id],
    entitiesByKey,
    nextSequence: event.sequence + 1,
    protocolError: null,
  };
}

export function replayRuntimeJournal(events: RuntimeJournalEvent[]): SandboxTraceState {
  return [...events].sort((a, b) => a.sequence - b.sequence).reduce(applyRuntimeJournalEvent, emptySandboxTrace());
}
