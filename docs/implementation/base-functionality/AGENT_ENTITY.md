# Agent Entity

## Purpose

`Agent` is the execution persona of the platform.

It solves user tasks using:
- versioned prompt and execution rules,
- allowed data assets,
- published runtime operations.

The agent layer must stay above discovery and provider infrastructure.

## Structure

### `Agent`

Stable container for:
- catalog identity,
- human-readable metadata,
- active version pointer.

### `AgentVersion`

Executable semantic version for:
- prompt parts,
- execution settings,
- safety constraints,
- optional access narrowing by instance.

## Core Rule

Agent must not consume:
- raw `DiscoveredTool`,
- provider-native tool names,
- provider contracts,
- sandbox-specific pseudo-entities.

Agent must consume:
- resolved data instances and collections from `CollectionResolver`,
- published `Operation` objects built by `ToolResolver` and operation publication logic.

## Relation To Tool Layer

Tool chain for agent:

1. `CollectionResolver` builds the agent-facing collection view
2. discovery creates `DiscoveredTool`
3. admin may leave it unpublished or link it to `Tool`
4. `ToolResolver` combines raw contract + effective `ToolRelease`
5. runtime binds capability to instance context
6. runtime publishes `Operation`
7. agent receives only resolved collection context and `Operation`

This keeps agent behavior stable when:
- raw provider slugs change,
- discovery descriptions are weak,
- one capability is reused across many instances.

## Responsibilities

Agent layer is responsible for:
- task identity,
- mission and scope,
- output behavior,
- execution controls,
- consuming published operations safely.

Agent layer is not responsible for:
- discovery,
- raw capability storage,
- tool publication,
- instance connectivity,
- credential delivery.

## Access Boundary

The agent works through runtime access boundaries:
- RBAC filters globally accessible instances,
- agent version may further narrow allowed instances,
- runtime builds operations only from the remaining allowed set.

So the agent does not manually bind raw tools.
It works with the already prepared runtime surface.

## Summary

`Agent` is the top-level semantic worker.

It should depend on:
- `Collection` and resolved data-instance context for data meaning,
- `Operation` for executable vocabulary,
- policy/runtime for enforcement.

It should not depend on discovery internals or provider-native capability names.
