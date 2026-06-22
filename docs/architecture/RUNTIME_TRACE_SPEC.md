# Runtime Trace Spec

## Purpose

Runtime trace is the operator-facing execution model for sandbox and admin tools. It is not a dump of transport events. It must let an AI engineer understand:

- what runtime entities participated in the run;
- what configuration and context each entity started with;
- what atomic execution steps happened under each entity;
- what each step received, produced, spent, and failed on.

## Canonical Model

Runtime trace has exactly two semantic layers.

### 1. Container entities

Containers provide hierarchy and context. They can have child entities and child steps.

Allowed container kinds:

- `run`
- `phase`
- `orchestrator`
- `planner`
- `agent`
- `dialog`
- `interaction`

Container lifecycle events must carry `entity_id`, `entity_type`, and `context_snapshot` when the entity starts.

### 2. Step events

Steps are atomic execution facts. They do not own other steps.

Allowed step kinds:

- `planner_decision`
- `llm_turn`
- `operation_call`
- `operation_result`
- `question_answer`
- `waiting_input`
- `confirmation_required`
- `final`
- `error`
- `status` only when it adds operator-meaningful state

Transport-only events such as `run_paused`, pause-related `stop`, `done`, and deltas are not business trace steps. They may exist on transport streams, but they must not become first-class persisted trace nodes.

## Parenting Rules

- Every step must either provide `parent_entity_id` explicitly or satisfy a deterministic documented fallback.
- Frontend tree assembly must not infer business ownership from unrelated payload fields when backend can provide it directly.
- `llm_turn` and tool IO must resolve under the planner/agent entity that initiated them.

## Snapshot Contract

`context_snapshot` is the canonical source for launch-time context. At minimum, container start events should populate:

- `inputs`
- `system_prompt` or prompt surface reference
- `rbac`
- `limits`
- `meta` with role/model/agent/tool availability

Frontend inspectors may derive presentation from snapshots, but they must not reconstruct missing execution semantics from raw payloads.

## Pause / Resume Contract

- `waiting_input` is the canonical trace event for clarify/ask-user pauses.
- `confirmation_required` is the canonical trace event for approval pauses.
- `question_answer` is the canonical trace event for the clarified Q&A step; frontend may group it under a `dialog` container together with the prompting LLM call(s).
- `run_paused` is transport state for live UI and persistence status sync; it is not a business trace step.
- pause-related `stop` is transport/lifecycle noise and must not be persisted as a separate trace step.
- resumed sandbox runs append to the same run with monotonic `order_num`.

## Thinking Contract

- planner thinking is a planner step, not a separate runtime role or entity.
- summaries-only reasoning is persisted:
  - hypotheses
  - selected hypothesis index
  - selected action kind
  - selected action summary
  - selection rationale
- full hidden chain-of-thought must not be stored or rendered.

## Frontend Reading Rules

- frontend reads one canonical stream of raw steps/events and normalizes them into semantic events;
- semantic events are assembled into one `TraceEntity` tree;
- container entities render container inspectors;
- atomic step entities render step inspectors;
- `dialog` is a logical container for clarification / question-answer flows; its children may include the LLM prompt that asked the question and the `question_answer` step that captured the response.
- sandbox and admin pages must share the same normalization, tree building, and inspector contracts.

## Inspector Contract

### Container inspector

Must show:

- info
- launch/config snapshot
- prompt surface
- RBAC/capability snapshot when present
- budgets / limits
- raw scoped payloads

### Step inspector

Must show:

- input
- output
- spend
- errors
- raw payload

## Summary Rules

Trace row labels must be operator-readable.

- `llm_turn` summary should prefer semantic purpose or selected action over `response_length`
- `waiting_input` should show the actual question
- `confirmation_required` should show the approval summary/message
- `planner thinking` should show the selected action summary

## Compatibility

- New runtime code must emit only canonical contracts.
- Historical traces may be adapted on read.
- Compatibility adapters must not justify continuing to emit legacy trace shapes.
