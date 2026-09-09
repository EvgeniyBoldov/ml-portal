# Execution graph

This companion note follows the immutable iteration runtime. The authoritative
specification is `docs/architecture/AGENT_RUNTIME.md`.

## Canonical model

An iteration contains immutable agent tasks and one terminal property:
`planner` requests the next iteration after all current tasks are terminal;
`synthesis` returns the final response only when every current task completed.

Planner and synthesis are terminal invocations, not task nodes. Failed,
blocked, cancelled, unfulfillable and `needs_dependency` tasks return control
to planner. That decision must explicitly continue the work, accept named
partial outputs, exclude scope, or report the limitation.

`task_id` is immutable and unique within a run. Tasks are never replaced or
removed; later work uses new IDs. The persisted iteration proposal, attempts,
dependencies, needs, bindings and resolutions form the audit trail.

The trace shows iterations and agent tasks, their dependencies, executor,
status and safe result summaries. It has no parallel patch/revision graph.
