# Sandbox Runtime

## Purpose

Sandbox is an admin-only overlay over the real runtime.

It exists to let operators change runtime values without introducing a second execution model.

## Core Rule

Sandbox may override values, but it must not redefine runtime behavior.

Sandbox is not a generic editor for database rows. It is a structured browser for runtime-relevant entities and their overrideable fields.

The resolver is the source of truth for what can be edited in sandbox.

## Resolver Contract

`SandboxOverrideResolver` is the canonical boundary between stored values and sandbox values.

It should expose only entities and attributes that:
- participate in runtime resolution,
- can be safely overridden without breaking contracts,
- are already consumed by runtime or sandbox flow.

It should not expose:
- RBAC rules as editable sandbox state,
- raw data rows,
- credentials,
- generic admin-only metadata that does not influence runtime behavior.

The resolver may still surface read-only summaries for related entities, but overrides must stay on the runtime side.

Allowed overrides:
- prompt fragments,
- tool semantic release fields,
- versioned semantic fields,
- model aliases,
- retry and timeout values,
- execution flags already known to runtime,
- other runtime-safe fields that are explicitly registered by the resolver.

Tool-specific rule:
- tool input/output schemas are read-only in sandbox,
- schemas and executable dispatch remain bound to the active `DiscoveredTool` / provider contract,
- branch semantic overrides apply to the resolved capability title and description, and may tighten risk, side effects, idempotency and confirmation,
- risk, side-effect and confirmation overrides may tighten but never weaken the discovered/runtime contract; idempotency can only be disabled,
- credential scope remains read-only because it changes credential selection,
- `published=false` removes the capability from that branch's resolved operations; `published=true` cannot add a capability that discovery, canonical publication or access checks did not resolve,
- ToolRelease selection is read-only until runtime dispatch can safely bind a selected release to an executable implementation. Missing or archived release IDs are therefore not accepted as effective runtime configuration.

## Resolver Tree Model

Sandbox should work with the same resolver object model that runtime uses.

Conceptually the resolver has three layers:

1. `Base state`
- the canonical values stored in DB
- this is the original runtime tree

2. `Branch overlay`
- sandbox branch overrides stored in branch-scoped tables
- this is the editable layer

3. `Effective state`
- `base + overlay`
- this is what sandbox preview and runtime execution consume

The resolver must be able to expose, for every relevant field:
- `base_value`
- `override_value`
- `effective_value`

This makes reset/diff/preview behavior deterministic and keeps the UI and runtime aligned.

## Fact memory overlay

The durable fact contract and post-turn writeback pipeline are defined in
[`RUNTIME_MEMORY.md`](RUNTIME_MEMORY.md). Sandbox uses only the overlay part of
that contract: it never turns a branch preview into a direct durable-memory
write.

Durable runtime facts have three scopes: `user`, `tenant` and `project`. Chat writes
them to the canonical `facts` table. Sandbox never writes that table: each
branch stores only an overlay keyed by `(scope, subject)` in its branch state.

- `set` replaces a durable fact for the branch or adds a branch-only fact;
- `deleted` is a tombstone that hides the durable fact for the branch;
- reset removes the overlay entry and restores the durable value.

The sandbox fact inspector exposes grouped `base`, `overrides`, and `effective`
views for all scopes. Fact overlays are included in the immutable run snapshot;
the runtime must resolve memory from that snapshot rather than mutable branch
state. Conversation summary storage remains for compatibility but is currently
disabled as a runtime memory component.

The sandbox may store overrides in branch-scoped persistence, but it should interact with the resolver as a structured tree, not as a flat form over database rows.

For tools, the resolver treats `published` as a branch-scoped capability filter:
- `published=false` removes an otherwise-resolved capability from operations in that branch
- `published=true` preserves an otherwise-resolved capability, subject to discovery, canonical publication and RBAC/access checks

This does not change global publication state in the registry or admin area. The runtime records configured and effective semantic values on the resolved operation snapshot.

Disallowed changes:
- routing logic,
- policy logic,
- RBAC logic,
- discovery logic,
- publication logic,
- tool execution algorithms,
- planner behavior.

## UI Shape

The sandbox UI should render a structured tree, not a flat list.

Recommended layout:
- left panel: runtime entities grouped by domain and layer,
- right panel: selected entity fields and current effective values,
- overlay editor: supported overrides for the selected field set,
- live preview: compiled effective config used by the runtime.

The left panel should show discovered tools grouped by runtime context.
Each tool item should indicate publication state:
- published
- draft/unpublished

The right panel should show the selected discovered capability, its read-only release inventory, the branch publication toggle and semantic/runtime-safe fields. Release selection stays read-only until runtime can execute that exact release.

Run inspector contract:
- `memory.search` shows retrieved document passages in its response tab and has
  no separate memory tab. Native HippoRAG passage `text` and source references
  also populate the owning executor's long-term memory group alongside facts.
- inspector selects an entity and compact semantic tabs; reusable domain Viewers
  render prepared plan, request, response, result, limits and access models;
- the projection exposes presentation entities `stage`, `step`, `executor`,
  `call` and `error`; wire names such as `planner_iteration` remain journal
  compatibility details and never determine inspector navigation;
- each projected executor carries its curated terminal result (status, safe
  message, output, dependencies, artifacts and operation counters); result
  Viewers render that model and never search journal events themselves;
- the projection assigns stage (`iteration`, memory preparation/writeback,
  synthesis), step and executor presentation kinds and returns the ordered tab
  policy with the selected target. The inspector renders that policy and does
  not branch on an executor slug;
- LLM and tool calls use `Инфо`, `Запрос`, `Ответ` or `Ошибка`, `RAW`; result
  and error are mutually exclusive, and an unavailable terminal result is not
  exposed as an empty tab;
- `TraceCall` exposes typed request, response, error and compact info models to
  semantic Viewers. Unknown payload fields are not projected into semantic
  tabs and remain available only in RAW;
- planner uses `Инфо`, `План` and applicable snapshot tabs; an agent uses
  `Инфо`, `Задача`, an available `Результат` and applicable snapshot tabs;
  memory/fact executors expose `Память`/`Факты` only when their projection has
  data; synthesizer exposes an available `Результат` and applicable snapshot
  tabs; a planner checkpoint exposes a dedicated `Решение` tab with declared
  and effective next route, decision reason and iteration;
- specialized snapshot tabs (`Промпт`, `Доступ`, `Лимиты`, `Валидация`) are
  data-aware and hidden when their source was not recorded. `RAW` is the stable
  final diagnostic tab for every selectable entity;
- executor-level `Prompt`, `RBAC`, `Limits` and `Preflight` are separate typed
  tabs. `Prompt` shows the effective system prompt for the execution; the LLM
  request retains the concrete message list for that call;
- an executor's `Инфо` tab is a compact record of work performed
  (LLM/tool calls, retries, errors, and separately labelled input, output and
  total token usage). Its `Лимиты` tab contains only
  locally configured executor limits and their usage; run-wide budgets are not
  repeated for every executor;
- a failed planner iteration exposes a localized failure summary and the
  recorded error code when the failed plan is linked to an applied plan from
  the same orchestrator. The UI does not invent an error message when runtime
  recorded only a code;
- access, limits, extraction and memory context are normalized by the trace
  projector before rendering. Their Viewers receive only typed models and do
  not parse journal payloads or reconstruct relations; extraction keeps a
  bounded result model while the complete source event remains in `RAW`;
- fields are typed (`datetime`, `duration`, status label, json, text, number,
  boolean). RAW renders one source journal event per read-only JSON field;
- UUID-only payloads and technical timestamps are noise in ordinary tabs;
  backend event payloads must provide human-readable operator fields.
- Run-level answer state is projected by the same trace projector into a typed
  `TraceRunView`: terminal content takes precedence over streamed deltas,
  attachment references are validated and deduplicated, safe errors and pause
  state are normalized, and the latest run budget snapshot is exposed as a
  bounded limits model. Chat rendering consumes this model; it does not scan
  journal payloads for final content or attachments. RAW remains the diagnostic
  escape hatch for the complete source events.
- A call response with `terminal=false` remains in progress and must not complete
  its owning executor. Executor completion comes from its lifecycle/result
  event, not from the latest successful LLM call. Run-level answer projection
  ignores intermediate executor finals once the run is failed, cancelled or
  aborted. A completed canonical `final_answer_marker` remains visible even
  when the run later ends failed; the chat shows that answer and the run error
  separately so partial success is preserved without hiding the failure. A
  resolved `question_answer` also closes the earlier pause state.
- Retry journal events carry the owning `llm_call_id` and are attached to that
  call. Stage retry counts aggregate owned events instead of counting every
  retry that happens to fall between the stage's first and last sequence.
- Semantic result sanitization removes journal internals and private storage
  URIs while preserving domain payloads such as `data`, `content`, source
  references and domain identifiers. Request views retain native tool call
  definitions and typed response schema details when logged.
- Extraction result projection merges start and terminal payloads so file and
  parser metadata survive completion. Interaction response views use the
  recorded answer payload, including structured answers.
- Agent version model and temperature overrides are applied by execution config
  resolution; `never_do` and `allowed_ops` are compiled into the effective
  prompt. Metadata-only notes are read-only in the sandbox, and tags are not
  offered as runtime overrides.

### Trace tab presentation contract

A semantic tab is a curated, typed view of a selected entity, not an automatic
dump of its payloads. For every entity inspector and every tab, the trace
projection defines a stable presentation schema: applicable source event types
and payload paths, field order, renderer, and the missing-data policy. The
schema selects only information useful for the tab's purpose; unknown or newly
logged fields remain available in RAW until a dedicated presentation model is
added.

The common `Info` tab is deliberately compact: entity/call type, lifecycle
status, duration, attempts or call count, and compact usage when it fits. It
is not a catch-all context tab. Task, plan, request, result/error, prompt,
access, memory and facts tabs show only their own domain. Usage becomes a
separate Viewer/tab only when its independent metrics would overload `Info`.

Use typed renderers rather than generic JSON fields:

- status, type, kind, phase, risk and source use normalized human-readable
  labels/badges;
- datetime and duration use short localized display values; raw timestamps are
  diagnostic data and belong in RAW unless they are the subject of the tab;
- JSON and long text use the formatted read-only text/JSON viewer with a
  full-screen expansion action;
- limits, RBAC, usage, plan, evidence, facts and other structured domains use
  their own Viewer components, never a list of arbitrary payload keys.

Each selected field is either `optional` (hidden when absent), `expected`
(shown as `Нет данных` when absent), or `required` (shown as a presentation
contract issue). A Viewer must not search nearby events, infer values from
sequence order, or use a generic object-to-fields fallback to fill gaps. RAW
is always the final read-only tab and is the only universal raw-event view.

Good group boundaries:
- agent version,
- tool release/version,
- orchestration,
- platform settings,
- system roles,
- instance runtime view,
- collection runtime view.

Bad group boundaries:
- tool groups,
- raw admin-only CRUD containers,
- policy or RBAC documents as editable sandbox state.

## Runtime Flow

1. Start from production runtime context.
2. Resolve sandbox overrides through the same resolver used by runtime.
3. Apply a value-level overlay only to supported runtime fields.
4. Build the effective resolver tree and freeze it into a snapshot for the branch/run.
5. Resolve the same routing, policy, and execution layers.
6. Emit the same trace primitives as production, with higher visibility.

Paused-run rule:
- Text questions and boolean confirmations use the same requester-bound
  `RuntimeInteraction`, including a private checkpoint.
- An answer resumes the same sandbox run at its requester: TurnPreflight,
  planner checkpoint or task agent. Planner/task answers bypass TurnPreflight.
- The resume snapshot is copied and validated before the persisted transport
  pause is cleared. A matching signed token is required for a gated operation.
- `{"action":"answer","pause_id":"...","response":false}` is a negative
  answer. `{"action":"cancel","pause_id":"..."}` cancels the paused run.
  The dedicated cancel endpoint handles actively running executions.
- See [Runtime Interactions](./RUNTIME_INTERACTIONS.md) for the shared contract.

Snapshot rule:
- the run must use the immutable snapshot produced from the branch resolver state,
- the snapshot must include both resolver shape fingerprint and branch override payload,
- the runtime must never read mutable branch state after the snapshot is created.

## Why This Exists

This is the linking mechanism between operator debugging and the authoritative runtime path.
