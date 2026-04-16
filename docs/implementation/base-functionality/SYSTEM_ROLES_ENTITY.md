# System Roles Entity

## Purpose

This document defines system orchestration roles as a standalone platform concept.

It describes:
- what `triage`, `planner`, and `summary` roles are,
- their boundaries and contracts,
- how they connect to agent runtime without owning domain execution.

This document is intentionally limited to system roles.
It does not define full RBAC, operation metadata internals, or collection semantics.

## Definition

`System Roles` are internal orchestrator personas that manage runtime flow quality and control:
- `triage` decides execution path,
- `planner` decides only the next orchestration step,
- `summary` maintains compact context and execution journal.

They are not business agents and do not own domain-specific tool behavior.

## Role Responsibilities

### 1. Triage

Triage is the entry classifier for a user request.

It is responsible for:
- choosing one of: `final | clarify | orchestrate`,
- selecting path intent: direct answer, doc-backed answer, or delegated agent path,
- producing confidence and reasoning fields for traceability.

Triage is not responsible for:
- executing tools,
- validating tool schemas,
- bypassing permission boundaries.

### 2. Planner

Planner is a **next-step planner**, not a long-horizon multi-step planner.

This is intentional:
- models are limited,
- short-horizon planning is more stable,
- replanning on each step gives better control and recovery.

It is responsible for:
- selecting only one next action from allowed orchestration vocabulary,
- tracking phased progress against execution outline,
- avoiding loops and triggering controlled finalization.

Planner is not responsible for:
- direct domain tool execution as product behavior,
- direct access policy decisions,
- semantic normalization of discovered capabilities.

### 3. Summary

Summary is both:
- context compressor,
- step journal for planner stability.

It is responsible for:
- maintaining compact conversation state,
- preserving execution state needed for replanning,
- storing step-level history:
  - goal,
  - which agents were called,
  - with which task/input,
  - what result was returned,
- preserving key facts, open questions, and partial conclusions,
- reducing context size growth over long interactions.

Summary is not responsible for:
- policy decisions,
- routing decisions,
- execution of domain operations.

## Contracts

System roles must operate via strict structured contracts:
- typed input payloads,
- typed output payloads,
- validation and trace logging.

Contract discipline is required to keep orchestration stable across model changes.

For `summary`, contract should explicitly include execution-journal fields, not only free-form conversation compression.

## Relation To Agent Layer

System roles orchestrate the process around agents.
They do not replace agent entity responsibilities.

Agent remains the execution persona.
System roles provide flow control around agent execution.

Important boundary:
- system role logic must not depend on internal agent prompt structure,
- system role logic must not depend on internal tool implementation structure.

System roles consume normalized runtime views (available actions, execution journal, outcomes), not raw component internals.

## Relation To Policy Layer

System roles may propose actions.
Policy and runtime gates decide if actions are allowed.

System roles should never be the final authority for destructive/write execution.

## Non-goals

- no domain schema ownership,
- no direct RBAC ownership,
- no direct operation safety ownership,
- no per-tenant hardcoded branching in prompts as architecture.
- no dependency on specific agent/tool internal schema for basic orchestration logic.

## Stage Decision (Current)

For current base-functional stage:
- keep three roles explicit: `triage`, `planner`, `summary`,
- keep `planner` in next-step mode (single actionable step per iteration),
- extend `summary` to execution-journal role for anti-loop and better replanning,
- keep contracts structured and versionable,
- keep role boundaries strict so business-agent logic does not leak into orchestration roles,
- keep orchestration stable even when agent/tool internals evolve.
