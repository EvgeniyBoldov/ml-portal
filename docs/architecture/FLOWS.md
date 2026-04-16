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
1. Discover raw capability as `DiscoveredTool`.
2. Keep it unpublished or review it as draft candidate.
3. Link it to a `Tool` publication container when accepted.
4. Resolve effective semantic/runtime config through `ToolResolver`.
5. Map it to a canonical `OperationSpec`.
6. Apply deterministic `PublicationRule`.
7. Expose an instance-scoped `Operation`.

Binding rule:
- raw provider names never become planner vocabulary,
- runtime sees only canonical published operations built from raw contract + effective semantic release.

Operational note:
- discovery/rescan refreshes raw source schemas and tool descriptors,
- discovery alone does not publish anything,
- sandbox may temporarily publish a discovered draft candidate through branch overlay.

## 3. Runtime Routing Flow

Related entity docs:
- [Instance Entity](DATA_MODEL.md#instance)
- [Operation Entity](DATA_MODEL.md#operation)

Flow:
1. Resolve user, tenant, and agent context.
2. Resolve allowed instances and policies.
3. Resolve semantic profiles and available operations.
4. Produce execution targets.
5. Pass execution through `RuntimeControlPlane` for sandbox attachment, logging-level resolution, and trace/error persistence.
6. Run the operation loop with policy and trace controls.

Binding rule:
- planner works on allowed operations,
- runtime resolves execution targets, not raw tool slugs.

Collection resolution note:
- runtime should resolve collections through type-specific resolvers,
- local table, local document, and remote SQL catalog flows must stay explicit,
- adding a new collection type should require a new resolver path, not hidden branching in prompt assembly.
- retrieval contract for planner/LLM must use canonical names (`collection.document.search`, `collection.table.search`), while raw builtin slugs stay internal.

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

Tool publication note:
- unpublished discovered tools may exist in sandbox as draft runtime nodes,
- sandbox may override the `published` flag for the branch snapshot,
- runtime and RBAC should consume only the effective published set from the snapshot, not the raw discovery list.

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
1. Runtime stops on `waiting_input` or `waiting_confirmation`.
2. Pause context is persisted in `agent_run` and `chat_turn`.
3. User confirms or provides additional input.
4. Current production path resumes by creating a new continuation turn in the same chat.
5. New run uses the accumulated chat history as context.

Binding rule:
- pause/resume is part of the chat execution contract,
- true checkpoint resume is a separate future capability and should not be implied by the current flow.

## 8. Why This Document Exists

These flows are the linking mechanisms between entity descriptions and runtime behavior.

They are intentionally lightweight:
- not a roadmap,
- not a migration plan,
- not a task list.

## 9. Planner Memory Contract

Flow:
1. Planner keeps bounded working context in `RunContextCompact`.
2. Planner persists execution memory in `ExecutionMemoryService`.
3. `RunContextCompact` is used only for prompt assembly and loop control.
4. `ExecutionMemoryService` is used for persistence, observability, and resume.

Binding rule:
- `RunContextCompact` is short-lived and bounded in-memory state,
- `ExecutionMemoryService` is durable run memory and may store a longer history.
