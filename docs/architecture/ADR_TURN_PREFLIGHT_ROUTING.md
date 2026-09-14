# ADR: TurnPreflight Routes a User Turn Before Planning

## Status

Accepted — implemented.

## Decision

`TurnPreflight` is a system LLM role at the root of every user turn. It is a
request router and normalizer, not an agent executor and not the existing
technical `ExecutionPreflight` that prepares an already selected agent.

```text
user message
  -> mechanical glossary/entity/project lookup
  -> TurnPreflight
     -> synthesizer
     -> planner -> agents -> synthesizer
     -> scoped recall -> TurnPreflight -> synthesizer
     -> clarify
  -> FactExtractor -> FactCompactor -> Reconciler
```

The mechanical lookup is code-only and bounded by ACL. It resolves only
candidate glossary aliases, projects and entities so that TurnPreflight does
not have to guess internal terminology. It does not supply unrestricted fact
values or act as an LLM tool loop.

TurnPreflight returns one strict `TurnPreflightDecision`:

- `route=synthesis` with a `SynthesisBrief`; runtime invokes synthesizer
  directly and creates no plan or synthetic agent task;
- `route=planner` with a `TaskBrief`; runtime invokes planner, which creates
  only real agent work;
- `route=recall` with a bounded `MemoryRequest`; runtime reads allowed context
  and invokes TurnPreflight once more to produce `synthesis` or `planner`;
- `route=clarify` with one question and continuation context. It reuses the
  standard `waiting_input` interaction contract but creates no plan or task.

`TaskBrief` normalizes the goal, project/entity hints, task direction,
constraints and expected result. It is not a plan. `SynthesisBrief` is the
same user-answer contract consumed by synthesizer after agent execution.
`MemoryRequest` limits recall by project, direction, kinds, entities and query
terms; runtime enforces scope, permissions, bounds and audit.

Planner owns on-demand contextual work for an execution request. It uses the
canonical scoped memory operations to resolve and read the rules, processes
and facts needed for a plan; project memory is not pre-injected as a planner
prompt dump. Agents use the same bounded operations only within their task
context.

TurnPreflight may propose evidence references and user/tenant durable-memory
candidates, including explicit terminology updates. These are hints, not
writes and not proof. Project semantic memory remains source-backed and is
published only by document ingestion. After the final answer the normal writeback pipeline independently
validates primary user/tool evidence and runs `FactExtractor`,
`FactCompactor` and reconcilers. A response may therefore say that a candidate
was submitted for verification, never that preflight persisted it.

## Consequences

- Simple questions avoid planner and empty agent tasks but still use
  synthesizer for the final user-visible answer.
- Project-memory answers may require one additional TurnPreflight call after
  bounded recall; agent work is still avoided.
- Planner is no longer the sole root routing decision-maker. It remains the
  sole producer of persisted `IterationProposal` and the owner of execution
  recovery decisions.
- Runtime trace gains a root `turn_preflight` entity and explicit route/recall
  decisions. Existing agent `ExecutionPreflight` trace events retain their
  current meaning.
