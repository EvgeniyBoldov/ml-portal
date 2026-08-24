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
- they come from `DiscoveredTool` or backend release data,
- only semantic/runtime fields of effective `ToolRelease` may be overridden in branch state,
- unpublished `DiscoveredTool` may be temporarily exposed as draft publication candidate in branch state.

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

For tools, the resolver should treat `published` as an overrideable runtime-safe flag within the sandbox branch overlay:
- `published=false` means capability stays only in discovery inventory for that branch
- `published=true` means capability is visible to runtime for that sandbox branch snapshot

This does not change global publication state in the registry or admin area.

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

The right panel should show the selected effective tool release or draft candidate, including the publish toggle and semantic/runtime-safe fields.

Run inspector contract:
- inspector selects an entity and compact semantic tabs; reusable domain Viewers
  render prepared plan, request, response, result, limits and access models;
- the projection exposes presentation entities `stage`, `step`, `executor`,
  `call` and `error`; wire names such as `planner_iteration` remain journal
  compatibility details and never determine inspector navigation;
- each projected executor carries its curated terminal result (status, safe
  message, output, dependencies, artifacts and operation counters); result
  Viewers render that model and never search journal events themselves;
- the projection assigns stage (`plan_revision`, memory preparation/writeback,
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
  tabs;
- specialized snapshot tabs (`Промпт`, `Доступ`, `Лимиты`, `Проверка`) are
  data-aware and hidden when their source was not recorded. `RAW` is the stable
  final diagnostic tab for every selectable entity;
- executor-level `Prompt`, `RBAC`, `Limits` and `Preflight` are separate typed
  tabs. `Prompt` shows the effective system prompt for the execution; the LLM
  request retains the concrete message list for that call;
- an agent executor's `Инфо` tab is a compact record of work performed
  (LLM/tool calls, retries, errors and tokens). Its `Лимиты` tab contains only
  locally configured executor limits and their usage; run-wide budgets are not
  repeated for every executor;
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
- `waiting_input` and `waiting_confirmation` are persisted sandbox-run states,
  not completed runs. Their pause action/context remain available until the
  run is resumed or cancelled.
- Resume continues the same sandbox run and clears the persisted pause only
  after its immutable resume checkpoint has been constructed.
- A paused run is cancelled by the common resume payload
  `{ "action": "cancel" }`; the dedicated cancel endpoint is only for an
  actively running execution. Aborting a browser stream is not a cancellation
  signal.

Snapshot rule:
- the run must use the immutable snapshot produced from the branch resolver state,
- the snapshot must include both resolver shape fingerprint and branch override payload,
- the runtime must never read mutable branch state after the snapshot is created.

## Why This Exists

This is the linking mechanism between operator debugging and the authoritative runtime path.
