# Runtime Trace Workbench Plan

## 0. Goal

Build a single semantic trace model for production agent runs and sandbox runs.

The target user is an AI engineer who needs to read execution logic, understand why the runtime made each choice, and find defects in prompts, routing, tools, policy, budgets, and model responses.

This plan intentionally does not preserve the old raw step-list UI as a first-class path. Raw JSON remains available only as a drill-down artifact.

## 1. Target Architecture

- [ ] Define one canonical trace contract: `RunTrace -> Phase[] -> Iteration[] -> SemanticEvent[] -> Artifact[]`.
  - Task: create the shape used by both `admin/agent-runs` and sandbox run details.
  - Done when: both production and sandbox run APIs can return the same semantic trace structure with source raw events attached.

- [ ] Normalize raw runtime events into semantic events before rendering.
  - Task: map `user_request`, `budget_policy`, `llm_call`, `protocol_retry`, `operation_call`, `operation_result`, `budget_consumed`, `final_response`, `planner_step`, `status`, `error`, and future events into stable semantic categories.
  - Done when: UI components no longer branch directly on raw `step_type` except in the raw payload viewer.

- [ ] Keep rendering separate from normalization.
  - Task: implement a semantic trace builder in a shared runtime-trace layer and renderers that consume only normalized trace objects.
  - Done when: admin and sandbox UIs import the same semantic trace types/helpers and do not duplicate event parsing rules.

- [ ] Use different views over the same trace model.
  - Task: production run page renders forensic diagnostics; sandbox renders experiment-oriented diagnostics with branch/snapshot/override context.
  - Done when: both pages show the same phases, iterations, budget, LLM, operation, and error semantics with different surrounding layout.

## 2. Checklist

### Step 1. Canonical Semantic Trace Contract

- [x] Define frontend and backend-facing trace types.
  - Task: introduce explicit types for `RunTrace`, `TracePhase`, `TraceIteration`, `SemanticEvent`, `TraceArtifact`, `BudgetSnapshot`, `RuntimeRef`, and `RawEventRef`.
  - Done when: the contract can represent existing `agent_run_steps` and `sandbox_run_steps` without losing raw payload access.

- [x] Define required semantic fields per event.
  - Task: every semantic event must expose `id`, `raw_type`, `category`, `title`, `summary`, `status`, `phase`, `iteration`, `started_at`, optional `duration_ms`, `inputs`, `outputs`, `decision`, `budget`, `refs`, and `raw`.
  - Done when: a renderer can show useful information without inspecting raw JSON.

- [x] Define stable categories.
  - Task: use categories `input`, `budget`, `llm`, `decision`, `retry`, `operation`, `policy`, `planner`, `final`, `error`, `system`.
  - Done when: every known raw step type maps to exactly one category and unknown types map to `system` with raw details.

- [x] Define iteration grouping rules.
  - Task: group events by explicit `step`, `iteration`, or `_envelope.sequence`; fall back to chronological order.
  - Done when: an execution like `llm_call -> protocol_retry -> llm_call -> operation_call -> operation_result -> budget_consumed` appears as readable iterations.

### Step 2. Backend Trace Builder

- [x] Add backend semantic trace builder for agent runs.
  - Task: build `RunTrace` from `AgentRun` + `AgentRunStep[]`.
  - Done when: `GET /admin/agent-runs/{id}` or a dedicated trace endpoint returns semantic trace data for real stored runs.

- [x] Add backend semantic trace builder for sandbox runs.
  - Task: build the same `RunTrace` from `SandboxRun` + `SandboxRunStep[]`.
  - Done when: sandbox run detail returns semantic trace data using the same contract as agent runs.

- [ ] Enrich refs server-side.
  - Task: resolve common UUIDs into labels for agent, tenant, user, chat, branch, snapshot, collection, operation, model, and tool where available.
  - Done when: semantic payloads avoid UUID-only surfaces for common runtime entities.

- [ ] Parse operation arguments/results into structured artifacts.
  - Task: convert JSON string arguments/results into objects when valid, keep raw text when invalid.
  - Done when: operation cards can show `collection_slug=reglament` as parameters instead of escaped JSON strings.

- [ ] Summarize budgets per run and per iteration.
  - Task: derive max, consumed, remaining, and limit breach data from `budget_policy`, `budget_consumed`, and `budget_limit_exceeded`.
  - Done when: the trace includes a budget timeline without UI recalculating raw payloads.

- [ ] Detect stale running runs.
  - Task: define stale rules for `running` runs with no updates or zero steps after timeout.
  - Done when: API marks such runs as `stale` or exposes `derived_status` without pretending they are actively running.

### Step 3. Runtime Logging Contract Cleanup

- [ ] Remove legacy event vocabulary from new logging paths.
  - Task: standardize runtime logs on `operation_call` and `operation_result`; do not add new `tool_call/tool_result` writes.
  - Done when: new runtime writes use canonical operation vocabulary and tests assert it.

- [ ] Add semantic hints at write time.
  - Task: include `phase`, `iteration`, `operation_slug`, `operation_label`, `agent_slug`, `model`, `reason`, and refs in emitted step payloads when known.
  - Done when: trace builder does not need fragile inference for common events.

- [ ] Store LLM request/response artifacts according to logging level.
  - Task: brief logs keep sizes, hashes, model, response length, retry reason, and finish details; full logs include prompt/messages/response as artifacts.
  - Done when: brief mode is useful for diagnosis without leaking or bloating content, and full mode provides reproducible LLM inspection.

- [ ] Store operation input/output artifacts according to logging level.
  - Task: brief logs keep normalized params, preview, status, length/hash; full logs keep complete input/output within existing redaction/truncation limits.
  - Done when: operation cards are readable in brief mode and complete in full mode.

### Step 4. Shared Frontend Trace Layer

- [x] Create shared runtime trace domain.
  - Task: add shared types, formatting helpers, category labels, status tones, artifact renderers, ref formatting, and unknown-event fallback.
  - Done when: admin and sandbox import shared helpers instead of maintaining separate step dictionaries.

- [ ] Implement semantic trace renderer primitives.
  - Task: create reusable components for phase timeline, iteration block, semantic event row, budget meter, artifact panel, ref chips, and raw drawer.
  - Done when: both UIs can compose these primitives without duplicating parsing logic.

- [x] Replace raw step list in `admin/agent-runs`.
  - Task: render the detail page as trace overview + phase timeline + iteration/event diagnostics + raw drill-down.
  - Done when: the page answers what happened, why it happened, what was sent, what returned, and what budget was consumed.

- [x] Replace sandbox step rendering with the same semantic trace primitives.
  - Task: sandbox chat keeps conversation shape but step details use normalized phase/iteration/event renderers.
  - Done when: sandbox and admin show consistent event meaning while sandbox keeps branch/snapshot context.

### Step 5. AI Engineer UX Requirements

- [ ] Add run summary panel.
  - Task: show request, selected agent, final status, derived status, duration, model, operation count, LLM calls, final answer presence, and primary error.
  - Done when: the first screen identifies the run and the main failure/success signal without opening raw JSON.

- [ ] Add execution flow timeline.
  - Task: show phases in order: input, budget, planning/routing, LLM, retry/decision, operation, result, final/error.
  - Done when: the user can visually follow cause and effect across the run.

- [ ] Add per-iteration cards.
  - Task: each iteration shows LLM call, decision/retry, operation calls/results, and consumed budget.
  - Done when: repeated loops are understandable without reading chronological raw events.

- [ ] Add budget diagnostics.
  - Task: show max/used/remaining for agent steps, tool calls, wall time, retries, and limit breaches.
  - Done when: budget regressions are visible per run and per iteration.

- [ ] Add LLM diagnostics.
  - Task: show model, request artifact, response artifact, response length, finish/retry reason, native tool calling flag, and prompt hash.
  - Done when: prompt/response defects are inspectable from the trace.

- [ ] Add operation diagnostics.
  - Task: show operation slug/label, target collection/tool, normalized params, result summary, status, duration, errors, and raw artifacts.
  - Done when: tool and collection defects are visible without decoding escaped JSON.

- [ ] Add decision diagnostics.
  - Task: show routing decisions, planner rationale, policy decisions, retry reasons, blocked operations, and available alternatives.
  - Done when: the reason for choosing or not choosing an operation is explicit.

### Step 6. API and Data Migration Cleanup

- [ ] Remove old frontend assumptions from TypeScript API models.
  - Task: replace narrow old unions with canonical raw type support plus semantic trace models.
  - Done when: current real DB event types are valid types and no UI relies on obsolete `llm_request/tool_call` only.

- [ ] Remove duplicated step metadata dictionaries.
  - Task: delete separate per-page mappings once shared runtime trace metadata exists.
  - Done when: there is one source of labels, tones, and category behavior.

- [ ] Keep raw JSON as a drill-down artifact only.
  - Task: remove raw JSON as primary collapsed preview.
  - Done when: collapsed events show semantic summary and raw is opened explicitly.

- [ ] Decide historical data handling.
  - Task: support existing stored raw events through semantic builder; no legacy UI branch remains.
  - Done when: old stored runs render through the new semantic model or clearly show unknown semantic events with raw fallback.

### Step 7. Tests

- [x] Add backend unit tests for trace builder.
  - Task: cover representative agent-run sequences: normal operation flow, protocol retry, budget limit, operation error, stale running, and unknown step.
  - Done when: each fixture produces expected phases, iterations, categories, titles, refs, and budget values.

- [ ] Add backend unit tests for sandbox trace builder.
  - Task: cover `planner_step`, `status`, `operation_call`, `operation_result`, `delta`, `final`, `waiting_input`, and error flow.
  - Done when: sandbox trace output matches the same semantic contract.

- [x] Add frontend unit tests for shared trace helpers.
  - Task: cover label/tone formatting, ref formatting, artifact rendering decisions, and unknown event fallback.
  - Done when: helper behavior is stable without browser-only tests.

- [ ] Add component tests for trace renderer.
  - Task: render a fixture with retry, operation result, budget consumed, and raw drawer.
  - Done when: visible text proves the UI is semantic, not raw JSON first.

- [ ] Add browser smoke checks.
  - Task: verify `/admin/agent-runs/{id}` and sandbox session run details against seeded or existing runs.
  - Done when: both pages show readable phase/iteration/event flow on desktop and mobile widths.

### Step 8. Documentation

- [ ] Document semantic trace contract.
  - Task: add contract notes to architecture docs with event categories, phases, artifacts, and refs.
  - Done when: new runtime events can be added without guessing UI behavior.

- [ ] Document logging levels.
  - Task: define what `none`, `brief`, and `full` must preserve for AI engineer diagnostics.
  - Done when: brief/full tradeoffs are explicit and testable.

- [ ] Document AI engineer workflow.
  - Task: add a guide section for reading traces, finding prompt defects, tool defects, budget defects, and policy/routing defects.
  - Done when: a new engineer can use the workbench without learning raw event internals first.

## 3. Non-Goals

- [ ] Do not keep the current raw chronological list as the main UI.
  - Task: raw chronological events remain available only as a raw/debug tab or drawer.
  - Done when: primary diagnosis uses semantic phases and iterations.

- [ ] Do not create a separate sandbox-only trace model.
  - Task: sandbox-specific context is an extension on the shared trace, not a parallel contract.
  - Done when: shared render primitives can consume both admin and sandbox traces.

- [ ] Do not make the frontend infer business meaning from arbitrary JSON forever.
  - Task: move durable semantic normalization into a shared builder/contract.
  - Done when: UI inference is limited to display formatting.

- [ ] Do not preserve legacy type names as the target vocabulary.
  - Task: standardize on canonical operation/runtime vocabulary and support old names only through normalization.
  - Done when: new code does not introduce new `tool_*` assumptions for runtime operation execution.

## 4. Release Criteria

- [ ] Real stored agent run with `protocol_retry` renders as a readable iteration with retry reason and available operations summary.
- [ ] Real stored operation call/result renders operation slug, normalized params, result preview, status, and raw artifact.
- [ ] Budget policy and budget consumed render as budget diagnostics, not raw JSON.
- [ ] Stale `running` runs no longer appear as healthy active execution.
- [ ] Sandbox run renders the same semantic flow while preserving branch and snapshot context.
- [ ] Raw JSON is still available for every event, but not the default collapsed representation.
- [ ] Type-check and relevant unit/component tests pass in containers.
