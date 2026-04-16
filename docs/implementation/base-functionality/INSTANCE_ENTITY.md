# Instance Entity

## Purpose

This document defines the `Instance` entity as a standalone platform concept.

It describes:
- what an instance is,
- what responsibilities belong to the instance layer,
- how instance classification works,
- how instances relate to collections, credentials, and runtime,
- where semantic description is required and where it is derived or absent.

This document is intentionally limited to the `Instance` entity itself.
It does not define the full operation registry, tool publication strategy, or planner behavior.

## Definition

An `Instance` is a unified declarative representation of a platform resource.

An instance does not represent raw storage or raw code directly.
It represents a normalized resource abstraction that allows the platform to work with different resource types through one common model.

An instance may describe:
- a data source and the way to access it,
- a service/tool provider and the way to access it,
- a model provider and the way to access it.

The instance layer exists so that the runtime can work with a common resource abstraction instead of special-casing every storage type, integration, or provider.

## Responsibilities

The instance layer is responsible for:
- declaring a resource in normalized form,
- identifying its role and classification,
- defining whether the resource is local or remote,
- storing connection and access information,
- linking credentials and authentication method,
- exposing runtime-facing identity for access control and operation resolution,
- connecting resource declarations with higher runtime layers.

The instance layer is not responsible for:
- defining the local structure of collection records,
- acting as the source of truth for local collection schema,
- replacing collection semantics for local collections,
- defining planner logic,
- acting as the primary definition of every resource-specific lifecycle.

## Core Idea

`Instance` is a common platform abstraction for connectable resources.

This abstraction should be broad enough to cover:
- local data instances backed by collections,
- remote data instances backed by external systems,
- remote service instances such as MCP gateways,
- provider-like resources such as LLM endpoints,
- future resource types such as logs or new data backends.

This broad scope is intentional.
However, it does not mean all instances have the same lifecycle or the same required metadata.

The instance layer must therefore support one shared abstraction with clear subtype-specific rules.

## Instance Classification

An instance is classified across several dimensions.

### 1. Resource Role

`instance_kind` defines what kind of resource the instance represents.

Current kinds:
- `data`
- `service`

Meaning:
- `data` means the instance represents a data source usable for reading facts or records,
- `service` means the instance represents an executable provider or integration surface.

### 2. Placement

`placement` defines where the resource lives operationally.

Current placements:
- `local`
- `remote`

Meaning:
- `local` means the platform manages the resource internally,
- `remote` means the platform connects to an external system.

### 3. Domain

`domain` defines the subject specialization of the instance.

Examples:
- `collection.table`
- `collection.document`
- `jira`
- `netbox`
- `mcp`
- `llm`

Domain is transitional classification metadata.

Migration rule:
- domain may be used for grouping/admin UX during transition,
- runtime behavior must be resolved from explicit bindings/capabilities,
- domain must not be the primary behavioral switch for collection access logic.

## Collection-Backed Local Instances

Local collection-backed instances are the main bridge between collection storage and runtime access.

For local collections:
- the instance is usually derived from the collection lifecycle,
- the instance exposes the runtime-facing identity,
- the instance carries the access boundary,
- the instance is what agents and planner logic see.

For document and table collections, the collection should not become agent-accessible implicitly.
Access remains explicit through instance configuration and runtime policy.

## Access Path

An instance may include an access-path link such as `access_via_instance_id`.

This means:
- the data instance is the object the agent wants to use,
- execution may be routed through a provider/service instance,
- the runtime still resolves operations and policy in instance context.

For platform-managed local data instances, the canonical provider is `local-runtime`:
- `instance_kind = service`,
- `placement = local`,
- local data instances link to it via `access_via_instance_id`.

## Instance Structure

An instance consists of four logical parts:

### 1. Identity And Classification

This describes the instance as a runtime resource.

Typical fields:
- `id`
- `slug`
- `name`
- `description`
- `instance_kind`
- `placement`
- `domain`
- `is_active`
- `health_status`
- `created_at`
- `updated_at`

### 2. Access Model

This describes how the resource is reached or invoked.

Typical fields:
- `url`
- `config`
- `access_via_instance_id`

The access model is also where credential binding and auth strategy are attached.

### 3. Runtime Publication Layer

This is the role of the instance as a resource visible to runtime.

The instance provides:
- a stable runtime identity,
- an RBAC target,
- a binding target for operations,
- a linkage point for credentials,
- a linkage point for provider access.

### 4. Optional Semantic Layer

The semantic layer is not universally required for all instance kinds.

At the current migration stage:
- semantic meaning is being moved to collection/data-asset level,
- instance-level semantic profile is a compatibility layer,
- service instances do not require semantic profile.

This is a deliberate restriction.
The platform should not force all instances into one universal semantic workflow.

## Relation To Collection And Operation Flows

Instance is the bridge between collection semantics and runtime execution.

Typical chain:
- `Collection` defines the local data product,
- `Instance` projects it into runtime,
- `Tool` or `Operation` publication turns it into executable actions,
- planner/runtime consumes only the resolved operation surface.

## Local And Remote Instances

Local and remote instances must be treated differently.

### Local Instances

A local instance is managed by the platform backend.

Examples:
- local collection-backed data instance,
- local internal knowledge resource,
- local internal service endpoint if needed.

For local collection-backed data instances:
- the collection remains the source of truth for the data structure,
- the local data instance is a derived publication/access object,
- semantics should be derived from the collection, not manually authored as a separate required object.

### Remote Instances

A remote instance is an external resource declared in the platform.

Examples:
- remote Jira data source,
- remote NetBox data source,
- remote MCP service,
- remote LLM provider.

Remote instances are primary admin-managed resources.
Their semantic or capability understanding cannot usually be derived from an internal schema object, because the platform does not own the source entity directly.

## Relation To Collection

Collection and instance are related but not identical.

### Collection

`Collection` is the local data-layer entity.
It defines:
- local homogeneous dataset,
- collection type,
- record schema,
- field semantics,
- local operational state.

### Collection-Backed Local Data Instance

A local data instance backed by a collection is a derived resource declaration.

It exists so the runtime can work with the collection through the common instance abstraction.

This means:
- collection is the source of truth,
- local collection-backed instance is the runtime-facing projection,
- collection classification determines local instance classification,
- collection semantics should feed local instance semantics,
- local collection-backed instance should not require an independent manually authored semantic profile to become structurally valid.

## Relation To Credentials And Authentication

Credentials belong naturally to the instance layer.

The instance is the correct place to bind:
- connection endpoint,
- access method,
- credential scope,
- auth strategy,
- provider indirection.

This is true because access details are properties of the resource declaration, not properties of:
- collection schema,
- planner,
- agent definition.

Local instances may not need credentials at all.
Remote instances typically do.

## Relation To RBAC

Instance is a runtime access control boundary.

RBAC should operate over instances because:
- they are the normalized resource identity,
- they are what runtime resolves into accessible resources,
- they provide a stable abstraction regardless of whether the source is local or remote.

This means:
- permissions can be attached to instance identity,
- agent visibility can be filtered through allowed instances,
- runtime can reason about allowed resources without special-casing storage origin.

## Semantic Layer Rules

The instance layer must not require one universal semantic mechanism for every instance.

### Data Instances

Data instances may require a semantic layer because agents need to understand:
- what the source contains,
- what entities live there,
- when the source is useful,
- how to interpret filters and schema hints,
- what limitations or caveats exist.

### Local Data Instances

For local collection-backed data instances:
- semantic meaning should be derived from the linked collection,
- separate semantic authoring must not be required for basic runtime readiness,
- an override mechanism may be introduced later if needed,
- but collection remains the primary semantic source.

### Remote Data Instances

For remote data instances:
- explicit semantic authoring is required,
- because there is no local collection entity from which semantic meaning can be derived,
- the semantic profile is the main way to explain the source to agent/runtime.

### Service Instances

At the current stage:
- service instances do not require a semantic profile,
- they may later require a capability-oriented description layer,
- but this is out of current scope,
- and should not be forced into the same model as data semantics.

This is a deliberate decision.
The platform should avoid introducing a generic semantic abstraction that does not provide strong present value.

## Mutability Rules

Instance mutability depends on instance class.

### Primary Admin-Managed Instances

Remote instances are primary admin-managed entities.
They may support normal updates to:
- name,
- description,
- connection details,
- config,
- active status,
- access linkage,
- other resource-level properties consistent with their class.

### Derived Local Collection-Backed Instances

Local collection-backed data instances are derived entities.

Their classification should be derived from collection state:
- `instance_kind = data`
- `placement = local`
- `domain = collection.table` or `collection.document`

Because of this:
- they should not be treated as fully free-form editable resources,
- their identity and classification should not drift away from the linked collection,
- collection remains the upstream source of truth.

## Current Special Cases

The current platform already contains several concrete instance patterns.

### 1. Local Collection-Backed Data Instance

This is a derived local instance that exposes a collection to runtime as a normalized resource.

Characteristics:
- derived from collection,
- data instance,
- local placement,
- domain depends on collection type,
- semantics should come from collection,
- not a primary manually authored resource.

### 2. Remote Data Instance

This is an external data source exposed as a normalized resource.

Examples:
- Jira data source,
- NetBox data source,
- future external structured or document backends.

Characteristics:
- primary admin-managed entity,
- explicit access model,
- may require credentials,
- requires explicit semantic description,
- participates in RBAC and runtime resolution.

### 3. Remote Service Instance

This is an executable provider or integration endpoint.

Examples:
- MCP gateway,
- LLM provider.

Characteristics:
- primary admin-managed entity,
- explicit access model,
- may require credentials,
- does not require data semantic profile by default,
- may later receive capability-oriented description if execution assistants become a real product need.

## Working Model

The intended working model of `Instance` is:

- instance is a normalized declaration of a platform resource,
- collections remain primary local data entities,
- local collection-backed instances are derived runtime-facing resource declarations,
- remote data instances are explicitly declared and semantically described,
- service instances are declared resources without mandatory data semantics,
- credentials and auth belong to instance layer,
- RBAC operates over instances as runtime resource identities.

## Practical Implications For Implementation

When implementing the instance layer, the system should avoid:
- treating all instances as having identical lifecycle rules,
- forcing all instance kinds through one semantic authoring workflow,
- making local collection-backed instances depend on manual semantic setup for structural validity,
- allowing derived local collection instances to drift from their source collection,
- mixing collection source-of-truth responsibilities into the instance layer.

The system should instead:
- keep instance as a shared resource abstraction,
- distinguish primary and derived instances,
- derive local collection-backed instance semantics from collection,
- require explicit semantic authoring only for remote data instances,
- keep service instances free from premature semantic complexity,
- use instance identity as the runtime access and RBAC boundary.

## Summary

`Instance` is the normalized resource declaration layer of the platform.

It provides a common abstraction for:
- local data resources,
- remote data resources,
- service providers,
- future resource classes.

It is broad by design, but not every instance kind follows the same lifecycle.

Collections remain the source of truth for local structured and document data.
Collection-backed local instances are derived runtime-facing resource declarations.
Explicit semantic authoring is required only where semantic meaning cannot be derived automatically, which currently means remote data instances.
