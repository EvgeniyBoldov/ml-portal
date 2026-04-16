# Operation Entity

## Purpose

`Operation` is the only runtime action vocabulary exposed to agent and planner.

It is not a raw discovered capability and not a stored semantic entity.
It is a runtime projection built from persisted entities and resolver logic.

## Definition

An `Operation` is an instance-scoped executable action formed from:
- `DiscoveredTool` contract,
- effective `ToolRelease` semantics,
- canonical publication mapping,
- instance/provider execution binding.

The operation is produced only after `ToolResolver` normalizes the tool view and publication rules are applied.

## Core Rule

Agents must consume `Operation`, not `DiscoveredTool` and not `ToolRelease`.

That means:
- discovery identity stays in infrastructure layer,
- semantic curation stays in versioned tool layer,
- runtime sees only the final published action.

## Structure

An operation must carry:
- stable runtime identity,
- canonical operation identity,
- readable name and description,
- input/output contract,
- data/provider instance binding,
- safety metadata,
- credential scope,
- execution target.

## Publication Chain

1. discovery refreshes `DiscoveredTool`
2. admin links or creates `Tool`
3. `ToolResolver` combines raw contract + effective `ToolRelease`
4. publication mapping resolves canonical operation meaning
5. runtime builds instance-scoped `Operation`

## Responsibilities

`Operation` is responsible for:
- planner-safe action vocabulary,
- final safety metadata used by policy,
- execution binding for one runtime instance,
- hiding provider-native noise from agent.

`Operation` is not responsible for:
- storing semantic versions,
- owning raw provider contracts,
- owning discovery lifecycle,
- replacing RBAC or credential systems.
