# Flows

## Purpose

This document describes the binding flows that connect the main entities of the platform.

It exists to explain how the platform moves from static model to runtime behavior without turning those flows into another roadmap.

## 1. Collection Lifecycle Flow

Related entity docs:
- [Collection Entity](DATA_MODEL.md#collection)
- [Instance Entity](DATA_MODEL.md#instance)

Flow:
1. Define collection metadata and canonical type.
2. Derive semantic meaning from metadata and schema.
3. Provision storage and operational state.
4. Materialize the collection-backed local instance.
5. Bind explicit visibility and access controls, including default permission set linkage where required.
6. Accept ingest in the type-appropriate form.
7. Publish readiness to runtime and admin UX.

Binding rule:
- collection owns local data structure and semantics,
- instance owns runtime identity and access boundary.

Operational note:
- if the collection is vector-enabled, vectorization happens after the initial table ingest,
- the collection should become ready for vector search only when vector artifacts exist,
- revectorization is a separate repeatable process, not a side effect of the first load.
- if the effective embedding model changes, runtime marks table rows as pending and performs full revectorization before continuing with fresh vectors.

## 2. Tool Publication Flow

Related entity docs:
- [Tool Entity](DATA_MODEL.md#tool)
- [Operation Entity](DATA_MODEL.md#operation)

Flow:
1. Discover the provider capability as an active `DiscoveredTool` snapshot.
2. Resolve the collection's data connector and execution provider.
3. Select that provider's active discovered tools and add collection defaults.
4. Normalize each descriptor through `ToolResolver`.
5. Build an executable `ResolvedOperation` with a collection-specific target
   binding.

Binding rule:
- provider tool names are the operation names exposed for that collection;
- provider URLs, credentials and execution bindings never become planner
  vocabulary;
- a new MCP capability does not require a product-code publication rule.

Operational note:
- discovery/rescan refreshes the provider's raw schemas and tool descriptors;
- discovery availability is scoped by the collection's provider relationship;
- sandbox may override runtime-safe fields, but does not create a second tool
  selection model.

## 3. Runtime Routing Flow

Related entity docs:
- [Instance Entity](DATA_MODEL.md#instance)
- [Operation Entity](DATA_MODEL.md#operation)

Flow:
1. Resolve user, tenant, and agent context.
2. Resolve allowed instances and policies.
3. Resolve semantic profiles and available operations.
4. Produce canonical operation descriptors and target-specific execution
   bindings.
5. Pass execution through `RuntimeControlPlane` for sandbox attachment, logging-level resolution, and trace/error persistence.
6. Run the operation loop with policy and trace controls.

Binding rule:
- planner works on allowed operations,
- runtime resolves execution targets for the already selected provider tools.

Collection resolution note:
- `CollectionRuntimeResolver` is the single target resolver;
- local `table`, `document` and `template` collections select an in-process
  provider by type;
- remote `sql` and `api` collections follow the relational
  `collection -> data_instance -> access_via/provider` chain;
- every collection-bound public operation requires `collection_slug`; the
  internal `collection_id` is resolved after access checks and is never part of
  the LLM-facing schema;
- publication exposes one canonical operation name even when several
  collection targets share the same provider; target-specific bindings remain
  internal to execution;
- adding a new collection type requires an explicit resolver/publication path,
  not hidden branching in prompt assembly.

## 4. Sandbox Overlay Flow

Related docs:
- [Sandbox Runtime](SANDBOX_RUNTIME.md)

Flow:
1. Start from the real production runtime context.
2. Resolve the base runtime tree from DB-backed entities.
3. Apply branch-scoped overrides through `SandboxOverrideResolver`.
4. Build the effective resolver tree with `base_value`, `override_value`, and `effective_value`.
5. Freeze the effective tree into a branch snapshot before run start.
6. Route the snapshot through `RuntimeControlPlane`, which attaches sandbox values to the runtime context.
7. Apply only supported runtime values that are explicitly registered by the resolver.
8. Preserve the same routing, policy, and execution logic.

Binding rule:
- sandbox may override only runtime-safe, resolver-registered values,
- sandbox may not redefine runtime behavior.

Tool resolution note:
- sandbox and runtime consume the same provider-first tool resolver;
- sandbox may override registered runtime-safe fields;
- raw discovery is never queried by frontend code or by a second resolver.

## 5. MCP Credential Delivery Flow

Related docs:
- [MCP Credential Flow](MCP_CREDENTIAL_FLOW.md)

Flow:
1. Runtime resolves an operation.
2. Runtime determines required credential scope.
3. Platform issues a short-lived credential payload or session link.
4. MCP provider consumes the secret for a limited session.

Binding rule:
- MCP transport is a delivery mechanism,
- credential ownership stays in the platform.

## 6. Chat Attachment Flow

Related docs:
- [Chat File Attachments](CHAT_FILE_ATTACHMENTS.md)

Flow:
1. User uploads file before message send.
2. Backend validates attachment and stores it in object storage.
3. Chat message references validated `attachment_ids`.
4. Runtime receives prompt-context derived from attachment metadata.
5. Assistant may emit generated files through the same attachment surface.
6. Download happens through unified file delivery.

Binding rule:
- runtime consumes validated attachment context, not raw request file bytes.

## 7. Pause / Resume Flow

Flow:
1. Runtime stops on a task-local `waiting_confirmation` or a root-level
   TurnPreflight `waiting_input` clarification.
2. Confirmation fingerprint stays in the runtime plan; root clarification
   context is persisted in `chat_turn` without a plan.
3. User answers a clarification or confirms/rejects that exact operation.
4. A clarification resumes the root turn at mechanical lookup and
   TurnPreflight without creating a plan. Confirmation resumes the same
   selected task; rejection is recorded as a
   `cancelled` task with the runtime-owned `confirmation_rejected` limitation
   and triggers the planner checkpoint.

Binding rule:
- pause/resume is part of the chat execution contract,
- a TurnPreflight clarification is a root interaction, never a paused plan or
  a synthetic agent task.

## 8. Why This Document Exists

These flows are the linking mechanisms between entity descriptions and runtime behavior.

They are intentionally lightweight:
- not a roadmap,
- not a migration plan,
- not a task list.

## 9. Turn Routing and Memory Contract

Flow:
1. Code resolves ACL-safe glossary aliases, projects and entities without an
   LLM call; values from durable memory are not injected at this stage.
2. `TurnPreflight` returns a strict `synthesis`, `planner`, `recall` or
   `clarify` decision. It provides a `SynthesisBrief`, `TaskBrief`,
   `MemoryRequest` or one clarification question respectively.
3. `synthesis` invokes Synthesizer directly. `recall` performs bounded scoped
   read and re-enters TurnPreflight once. `planner` invokes GraphPlanner.
4. Planner and agents use canonical scoped memory operations themselves;
   planner decides which recalled rules, processes and facts are relevant to
   the plan.
5. After every final synthesis, `finalize_memory` asynchronously runs
   `FactExtractor -> FactCompactor -> FactReconciler` and persists only
   evidence-backed candidates. TurnPreflight proposals are hints, not writes.

Binding rule:
- `RuntimeTurnState`/`TurnMemory` are short-lived bounded turn state,
- `MemorySnapshot` is the immutable read projection for one run,
- `TurnPreflight` never reads storage directly, creates plans/tasks or writes
  durable memory,
- `facts` is durable business memory; `runtime_execution_events` remains the
  execution journal and is not a memory store,
- sandbox overlays are branch-scoped and never directly persist durable facts.

## 10. Chat Context Materialization Flow

Related docs:
- [Chat Context Memory](CHAT_CONTEXT_MEMORY.md)
- [Chat File Attachments](CHAT_FILE_ATTACHMENTS.md)
- [Runtime Event Journal](RUNTIME_TRACE_SPEC.md)

Flow:
1. Load a bounded recent dialogue tail and the active typed chat-context
   snapshot.
2. Re-authorize selected artifact references through the canonical chat
   artifact service.
3. Freeze the bounded snapshot into the current runtime turn.
4. Execute the canonical runtime pipeline.
5. Build a typed `RuntimeOutcomeProjection` from runtime state, final plan
   state, verified artifacts, and safe limitations.
6. Register verified artifact targets in the chat artifact registry.
7. Apply deterministic chat-context operations in turn order.
8. Optionally compact goal/topic/decision context asynchronously with a
   revision guard.

Binding rule:
- `runtime_execution_events` is never an extraction input and is never
  replayed into chat memory;
- `chat_artifact_references` owns file identity, target resolution, and access;
- `chat_memory_items` owns only bounded conversational meaning and provenance;
- runtime plans remain control-plane state and contribute only typed bounded
  outcome references;
- technical errors remain diagnostics, while only safe continuation-relevant
  limitations may enter chat context.
