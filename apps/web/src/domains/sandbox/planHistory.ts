import {
  projectPlan,
  taskStatusLabel,
  type PlanCheckpointViewModel,
  type PlanEntry,
  type PlanTaskViewModel,
  type PlanViewModel,
} from './planInspection';
import type { RuntimeJournalEvent } from './traceState';

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const string = (value: unknown): string =>
  typeof value === 'string' ? value : '';
const planId = (event: RuntimeJournalEvent): string =>
  string(event.payload.plan_id) ||
  string(event.entity_id) ||
  string(event.payload.entity_id);
const iterationId = (event: RuntimeJournalEvent): string =>
  string(event.payload.iteration_id) ||
  string(event.parent_entity_id) ||
  string(event.payload.parent_entity_id);

/** Replay only the selected plan's recorded iterations. Later proposals must not alter earlier views. */
export function projectPlanHistory(
  events: RuntimeJournalEvent[],
  selected: RuntimeJournalEvent,
  selectedIteration: number
): { delta: PlanViewModel; full: PlanViewModel } {
  const selectedPlan = planId(selected);
  const proposals = events
    .filter(
      event =>
        event.event_type === 'plan_iteration_applied' &&
        event.run_id === selected.run_id &&
        (selectedPlan
          ? planId(event) === selectedPlan
          : event.id === selected.id)
    )
    .sort((a, b) => a.sequence - b.sequence);
  const past = proposals.filter(event => event.sequence <= selected.sequence);
  const next = proposals.find(event => event.sequence > selected.sequence);
  const cutoff = next ? next.sequence - 1 : Number.POSITIVE_INFINITY;
  const tasks = new Map<string, PlanTaskViewModel>();
  const groups: Array<{
    event: RuntimeJournalEvent;
    taskIds: string[];
    number: number;
  }> = [];
  const currentAffected: string[] = [];
  let incomplete =
    !selectedPlan ||
    (selectedIteration > 0 && past.length < selectedIteration) ||
    (selectedIteration === 0 && string(past[0]?.payload.trigger) !== 'initial');
  for (const [index, event] of past.entries()) {
    const current = event.id === selected.id;
    const number =
      selectedIteration > 0
        ? selectedIteration - past.length + index + 1
        : index + 1;
    const proposal = record(event.payload.proposal);
    if (!Array.isArray(proposal.tasks)) incomplete = true;
    const projected = projectPlan(event.payload);
    const replacements = new Map<string, string[]>();
    const resolutions = Array.isArray(proposal.resolutions)
      ? proposal.resolutions
      : [];
    for (const value of resolutions) {
      const resolution = record(value);
      const oldId = string(resolution.task_id);
      const action = string(resolution.action);
      const related = Array.isArray(resolution.replacement_task_ids)
        ? resolution.replacement_task_ids.filter(
            (id): id is string => typeof id === 'string'
          )
        : [];
      if (action === 'continue_with_tasks')
        for (const id of related)
          replacements.set(id, [...(replacements.get(id) ?? []), oldId]);
      const old = tasks.get(oldId);
      if (!old) {
        incomplete = true;
        continue;
      }
      const change =
        action === 'continue_with_tasks'
          ? 'superseded'
          : action === 'exclude_from_scope'
            ? 'excluded'
            : action === 'accept_partial'
              ? 'partial'
              : action === 'report_unresolved'
                ? 'unresolved'
                : undefined;
      if (!change) continue;
      tasks.set(oldId, {
        ...old,
        change,
        inactive: change === 'superseded' || change === 'excluded',
        relatedTaskIds: related,
        changeReason: string(resolution.reason) || undefined,
      });
      if (current) currentAffected.push(oldId);
    }
    for (const task of projected.tasks) {
      if (tasks.has(task.taskId)) {
        incomplete = true;
        continue;
      }
      const parents = replacements.get(task.taskId);
      tasks.set(task.taskId, {
        ...task,
        iterationNumber: number,
        ...(parents?.length ? { relatedTaskIds: parents } : {}),
        ...(current
          ? { change: parents?.length ? 'continuation' : 'new' }
          : {}),
      });
    }
    groups.push({
      event,
      taskIds: projected.tasks.map(task => task.taskId),
      number,
    });
  }
  // Status is reconstructed only up to the next applied iteration; a later replan
  // must not rewrite an earlier stage's picture.
  const statuses: Record<string, string> = {
    task_planned: 'pending',
    task_started: 'running',
    task_completed: 'completed',
    task_failed: 'failed',
    task_cancelled: 'cancelled',
    task_needs_dependency: 'needs_dependency',
    task_blocked: 'blocked',
    task_unfulfillable: 'unfulfillable',
    task_paused: 'waiting_input',
    task_resumed: 'running',
  };
  for (const event of events) {
    if (
      !selectedPlan ||
      event.run_id !== selected.run_id ||
      event.sequence > cutoff ||
      string(event.payload.plan_id) !== selectedPlan
    )
      continue;
    const taskId = string(event.payload.task_id);
    const task = tasks.get(taskId);
    const status =
      event.event_type === 'task_paused'
        ? string(event.payload.status) || statuses[event.event_type]
        : statuses[event.event_type];
    if (task && status)
      tasks.set(taskId, {
        ...task,
        status: taskStatusLabel(status),
        ...(status === 'cancelled' && !task.inactive
          ? { inactive: true, change: 'cancelled' as const }
          : {}),
      });
  }
  const checkpoints = new Map<string, PlanCheckpointViewModel>();
  for (const group of groups) {
    const id = iterationId(group.event);
    const relevant = events
      .filter(
        event =>
          event.run_id === selected.run_id &&
          event.sequence <= cutoff &&
          string(event.payload.plan_id) === selectedPlan &&
          string(event.payload.iteration_id) === id &&
          (event.event_type === 'checkpoint_planned' ||
            event.event_type === 'checkpoint_decided')
      )
      .sort((a, b) => a.sequence - b.sequence);
    const planned = relevant.find(
      event => event.event_type === 'checkpoint_planned'
    );
    const decided = [...relevant]
      .reverse()
      .find(event => event.event_type === 'checkpoint_decided');
    if (!planned) continue;
    checkpoints.set(id, {
      id: string(planned.entity_id) || string(planned.payload.checkpoint_id),
      iteration: group.number,
      declaredNext: string(planned.payload.declared_next) || undefined,
      effectiveNext: string(decided?.payload.effective_next) || undefined,
      reason: string(decided?.payload.reason) || undefined,
      decided: Boolean(decided),
    });
  }
  const entries: PlanEntry[] = [];
  const emitted = new Set<string>();
  const appendTask = (id: string) => {
    const task = tasks.get(id);
    if (!task || emitted.has(id)) return;
    emitted.add(id);
    entries.push({ kind: 'task', task });
    if (task.change === 'superseded')
      for (const replacement of task.relatedTaskIds ?? [])
        appendTask(replacement);
  };
  for (const group of groups) {
    for (const id of group.taskIds) appendTask(id);
    const checkpoint = checkpoints.get(iterationId(group.event));
    if (checkpoint) entries.push({ kind: 'checkpoint', checkpoint });
  }
  const deltaEntries: PlanEntry[] = [];
  const currentIds = groups[groups.length - 1]?.taskIds ?? [];
  const deltaSeen = new Set<string>();
  const addDelta = (id: string) => {
    const task = tasks.get(id);
    if (!task || deltaSeen.has(id)) return;
    deltaSeen.add(id);
    deltaEntries.push({ kind: 'task', task });
    if (task.change === 'superseded')
      for (const related of task.relatedTaskIds ?? []) addDelta(related);
  };
  for (const id of currentAffected) addDelta(id);
  for (const id of currentIds) addDelta(id);
  const currentCheckpoint = checkpoints.get(iterationId(selected));
  if (currentCheckpoint)
    deltaEntries.push({ kind: 'checkpoint', checkpoint: currentCheckpoint });
  const base = projectPlan(selected.payload);
  return {
    delta: {
      ...base,
      tasks: currentIds
        .map(id => tasks.get(id))
        .filter((task): task is PlanTaskViewModel => Boolean(task)),
      entries: deltaEntries,
      historyIncomplete: incomplete,
    },
    full: {
      ...base,
      tasks: [...tasks.values()],
      entries,
      historyIncomplete: incomplete,
    },
  };
}
