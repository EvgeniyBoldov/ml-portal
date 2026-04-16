# Policy Enforcement Entity

## Purpose

This document defines the `Policy Enforcement` layer as a standalone platform concept.

It describes:
- where policy decisions are applied,
- what policy inputs are required,
- boundaries between policy intent and policy enforcement,
- required enforcement points for scalable runtime safety.

This document is intentionally limited to enforcement architecture.
It does not define UI workflows for policy authoring.

## Definition

`Policy Enforcement` is the runtime gate layer that decides whether a proposed action may execute.

It consumes normalized metadata and produces a deterministic decision:
- `allow`,
- `block`,
- `require_confirmation`,
- `require_input`.

## Core Idea

Policy is not only text.
Policy enforcement must use structured inputs:
- platform gates/caps,
- agent-level constraints,
- operation safety metadata,
- execution context state.

Without structured inputs, policy remains declarative but not enforceable.

## Responsibilities

Policy enforcement layer is responsible for:
- evaluating proposed actions against active safety rules,
- applying side-effect/risk gates before execution,
- enforcing iteration/time limits and loop guards,
- returning explicit decision reasons for traceability.

Policy enforcement layer is not responsible for:
- discovering tools,
- generating operations,
- choosing business strategy,
- replacing RBAC.

## Required Inputs

Minimum required policy inputs:
- action intent (`agent_call|operation_call|...`),
- operation metadata (`side_effects`, `risk_level`, confirmation flags),
- platform gates (global forbid/confirmation settings),
- execution limits (steps/time/retries),
- run context (loop/iteration state).

## Enforcement Boundaries

Policy intent may exist at multiple layers:
- platform-level global rules,
- agent-level safety intent,
- operation-level safety metadata.

Final enforcement must happen immediately before action execution.

This means:
- orchestration-level checks are necessary but not sufficient,
- execution-time gate before concrete operation call is mandatory.

## Relation To RBAC

RBAC answers "who can access which resource".
Policy enforcement answers "which action can run now under current safety rules".

Both are required and non-substitutable.

## Relation To Planner And System Roles

Planner/system roles propose next actions.
Policy enforcement validates proposed actions.

Roles must not bypass policy decisions.

## Non-goals

- no prompt-only safety as final enforcement mechanism,
- no hidden fallback execution paths that skip policy checks,
- no duplication of policy logic across unrelated layers.

## Stage Decision (Current)

For current base-functional stage:
- keep policy enforcement as explicit runtime gate component,
- ensure decisions are based on normalized operation metadata,
- keep decision output deterministic and auditable.
