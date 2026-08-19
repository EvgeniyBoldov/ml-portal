# Collection-Asset Refactor

## Purpose

This document fixes the target model for data assets and runtime bindings.

The goal is to evolve the existing model without breaking runtime:
- keep `Collection` as the semantic/data-asset layer,
- keep `ToolInstance` as runtime access/connector layer,
- remove behavior-level dependency on `instance.domain`,
- unify local and remote collections under one resolution contract while
  keeping their provider selection rules explicit.

## Why This Refactor Exists

Current model already has most required pieces:
- `Collection` stores schema and collection metadata,
- `ToolInstance(data)` is runtime identity and access boundary,
- `ToolInstance(service)` is connector/provider access path,
- local collection flow auto-creates a data instance.

The mismatch:
- runtime/readiness paths still contain domain-based branches (`collection.*`),
- semantic profile for remote data lives on instance,
- local collection semantics are derived separately.

This creates mixed ownership and extra conditional logic.

## Target Model

### 1. Collection = Data Asset Scope

`Collection` is the semantic contract of data:
- schema and field semantics,
- asset description and use cases,
- readiness as data product,
- asset grouping (1:1 and 1:N both allowed).

`1:1` is a special case of `1:N`.

Examples:
- local structured collection: one table (1:1),
- SQL collection: set of related remote tables for one business scope (1:N),
- NetBox collection: set of entities like devices/racks/prefixes (1:N),
- Jira collection: set of entities like issues/comments/projects (1:N).

Collection must not store endpoint contracts.

### 2. ToolInstance = Access Layer

`ToolInstance(data)`:
- runtime identity,
- access path and credentials,
- optional link to service instance (`access_via_instance_id`).

`ToolInstance(service)`:
- connector/provider execution surface.

Instance is not the owner of data semantics.

### 3. Runtime Resolution Contract

Runtime resolves in this order:
1. public `collection_slug` to the semantic collection scope,
2. effective access and readiness for that collection,
3. local provider by `collection_type`, or the remote
   `data_instance -> access_via/provider` chain,
4. one canonical published operation with an internal target-specific binding.

The public operation contract is provider-agnostic. `collection_id` is an
internal persistence/runtime identifier and is not exposed to the planner or
LLM. Behavior is driven by collection type, relational source links and
capabilities, not by `instance.domain` or provider-qualified tool names.

## Domain Policy

`instance.domain` is transitional classification metadata only.

Rules:
- allowed as admin/UI grouping hint during migration,
- not allowed as behavior key for runtime/readiness decisions,
- should be gradually removed from operational logic.

## Migration Plan

### Phase 1 (started)

Objective: remove collection behavior checks from `domain`.

Implemented:
- introduced `CollectionRuntimeResolver` as the collection-first target
  resolver;
- local collection provider selection uses explicit `collection_type`;
- remote sources use the relational data-instance/provider chain;
- canonical publication and internal target bindings no longer use
  `instance.config.bindings` as runtime source of truth.

### Phase 2

Objective: move semantic ownership from instance to collection.

Tasks:
1. add versioned collection semantic profile entity/API,
2. keep instance semantic profile as compatibility fallback,
3. switch runtime semantic resolution priority:
   - collection semantic profile,
   - derived collection profile (fallback),
   - legacy instance profile (temporary).

### Phase 3

Objective: unify local and remote collection lifecycle.

Tasks:
1. define uniform collection creation/discovery flow:
   - local: admin defines schema, platform provisions storage,
   - remote: discovery imports entities/schemas into collection scope,
2. keep one invariant: every runtime-visible collection has a data instance binding.

### Phase 4

Objective: deprecate domain-coupled operation publication.

Tasks:
1. replace domain-driven publication mapping with binding/capability-driven mapping,
2. keep backward compatibility bridge for existing operation slugs.

Implemented:
- publication prefers discovered capability domains and canonical operation
  metadata; instance domain is only transitional fallback metadata;
- shared providers publish one canonical operation while execution retains
  collection-specific bindings.

### Phase 5

Objective: hard deprecation of domain in instances.

Tasks:
1. remove behavior dependencies on `domain`,
2. migrate admin/API contracts to explicit binding/capability fields,
3. then remove domain from storage and DTOs.

## Non-goals

This refactor does not:
- introduce new collection types immediately,
- redesign planner prompts,
- redesign tool release model,
- change endpoint contracts for existing local table/document flows in one step.

## Implementation Notes

Mandatory invariants during migration:
1. runtime must stay backward compatible with existing instances,
2. local collection flow must continue to auto-create data instances,
3. collection permission and instance permission checks must both remain enforced.
