# ADR: Runtime Trace Uses Entity Tree + Atomic Steps

## Status

Accepted

## Decision

Runtime trace is modeled as a tree of logical execution entities with atomic execution steps attached beneath them.

- Containers capture hierarchy and launch context.
- Steps capture one execution action with input/output/spend/error.
- Transport events are not promoted to business trace nodes unless they have operator meaning.
- Clarification flows are represented as a dedicated `dialog` container that may own the LLM question step and the `question_answer` step together.

## Why

Flat step logs do not explain ownership, scope, or launch context. They force engineers to reconstruct:

- which planner iteration chose an agent;
- which agent owned an LLM call or tool call;
- which prompt/RBAC/budget context applied when a step ran;
- whether a pause/resume event is business logic or stream transport.

The entity tree solves this by making hierarchy explicit and making inspectors role-specific.

## Consequences

- Backend must emit stable parent references and lifecycle snapshots.
- Frontend must have one normalization/tree pipeline shared by sandbox and admin.
- New runtime features such as thinking, memory components, and future sub-agents must extend the canonical trace contract instead of inventing parallel UI/event paths.
