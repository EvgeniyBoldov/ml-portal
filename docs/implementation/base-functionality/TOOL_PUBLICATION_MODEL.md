# Tool Publication Model

## Purpose

This document defines how raw discovered capabilities become agent-visible runtime operations.

Target model:
- `DiscoveredTool` = raw capability artifact
- `Tool` = publication container
- `ToolRelease` = curated semantic/runtime version
- `Operation` = final instance-scoped runtime action

`ToolResolver` is the prompt/runtime assembly layer for this chain.

## Core Rule

Discovery inventory is broader than runtime vocabulary.

Therefore:
- not every `DiscoveredTool` becomes a `Tool`,
- not every discovered capability is globally published,
- agent never consumes raw discovery output directly.

## Publication Pipeline

1. Discovery refreshes `DiscoveredTool`.
2. Capability may remain unpublished.
3. Admin may review it as a draft candidate.
4. If accepted, capability is linked to a `Tool`.
5. `ToolRelease` provides semantic/runtime metadata.
6. Publication rules map raw capability into canonical operation meaning.
7. Runtime builds instance-scoped `Operation`.

## Entity Roles

### `DiscoveredTool`
- raw source/provider artifact
- stores input/output contract and source linkage
- may exist without any published runtime representation

### `Tool`
- stable business/publication container
- groups semantic releases
- keeps active release pointer

### `ToolRelease`
- semantic/runtime source of truth
- stores safety, execution, routing, and LLM-facing metadata

### `OperationSpec`
- canonical operation meaning
- stable product vocabulary independent from provider-native naming

### `PublicationRule`
- deterministic mapping from raw capability + context to canonical operation

### `Operation`
- final runtime action visible to agent and policy

## Identity Rules

1. Raw discovery identity:
- `(source, provider_instance_id, discovered_tool.slug)`

2. Publication container identity:
- `tool.slug`

3. Semantic version identity:
- `tool_release.version`

4. Runtime action identity:
- `operation_slug = instance.<instance_slug>.<canonical_op_slug>`

Important rule:
- raw discovered identity must not become final planner vocabulary.

## Sandbox Rule

Sandbox may:
- override effective `ToolRelease` fields,
- temporarily publish an unpublished `DiscoveredTool` as a draft candidate,
- build a branch-local effective published set.

Sandbox may not:
- mutate raw discovery contracts,
- redefine execution adapters,
- create a second global publication registry.

## Deterministic Source Of Truth

Runtime should assemble operations from one clear split:
- raw contract from `DiscoveredTool`,
- curated semantics from effective `ToolRelease`,
- canonical meaning from `OperationSpec` + `PublicationRule`,
- instance binding from resolver.

This removes semantic duplication and keeps publication reviewable.
