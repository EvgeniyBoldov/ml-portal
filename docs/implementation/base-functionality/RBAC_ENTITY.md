# RBAC Entity

## Purpose

This document defines the `RBAC` layer as a standalone platform concept.

It describes:
- what RBAC controls,
- owner hierarchy and override model,
- how RBAC applies to any platform entity,
- where RBAC boundaries start and end.

This document is intentionally limited to access control semantics.
It does not define discovery, tool profiling, planner internals, or execution business logic.

## Definition

`RBAC` is a policy layer that controls visibility and usage rights of platform entities.

RBAC must support global defaults and explicit scoped overrides for rollout, staged enablement, and departmental access control.

## Core Rule: Override Priority

RBAC resolution priority is:
- `user` overrides `tenant`,
- `tenant` overrides `platform`.

In short:
- `user > tenant > platform`.

This rule is mandatory and applies to all supported resource types.

## Resource Scope

RBAC is resource-type agnostic by design.
It must support the same override strategy for any managed entity, including:
- agents,
- instances,
- tools/operations,
- collections,
- future resource types.

This enables controlled rollout patterns:
- deny at platform level by default,
- allow for one tenant for pilot,
- allow for one user for private testing.

In this product, `tenant` is closer to a company department or organizational slice than to a hard isolation boundary for tools and instances. Shared tools and shared instances can exist across departments, while RBAC still controls who can see or use them.

## Responsibilities

RBAC layer is responsible for:
- storing and resolving allow/deny decisions for resources,
- applying owner hierarchy with deterministic precedence,
- exposing effective permissions to runtime preflight,
- providing clear deny reasons for audit/runtime visibility.

RBAC layer is not responsible for:
- semantic interpretation of tools or collections,
- planner strategy,
- operation execution details,
- credential management.

## Decision Model

For each `(resource_type, resource_id)` and caller context:
- resolve explicit rule at user level if present,
- otherwise resolve tenant level,
- otherwise resolve platform level,
- otherwise default deny (unless product policy explicitly defines another default per resource class).

Resolution must be deterministic and idempotent.

## Relation To Runtime

RBAC output is an input for preflight/resolution layers.

Runtime must consume already resolved permissions, not raw RBAC rows.
Planner and agents must never bypass RBAC-resolved visibility.

## Rollout Use Cases

RBAC must support:
- hidden-by-default new agent/tool/instance rollout,
- tenant pilot enablement,
- per-user testing in production tenant,
- emergency deny override at higher scope where needed.

## Non-goals

- RBAC should not duplicate business validations from domain services.
- RBAC should not encode orchestration plans.
- RBAC should not replace operation-level safety metadata.

## Stage Decision (Current)

For current base-functional stage:
- keep one universal override model across entity types,
- enforce `user > tenant > platform` as invariant,
- keep default platform stance restrictive for new critical entities where required by release policy.
