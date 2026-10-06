# ADR: TurnPreflight Routes a User Turn Before Planning

## Status

Accepted — implemented.

## Decision

`TurnPreflight` is a system LLM role at the root of every user turn. It is a
request router and normalizer, not an agent executor and not the existing
technical `ExecutionPreflight` that prepares an already selected agent.

Direct synthesis requires certainty that the answer can be prepared entirely
from existing inputs. Possible execution, fresh data, checks, tools, artifact
creation, or uncertainty that requires investigation route to planner. Missing
parameters and unresolved external project names are handed to planner with the
original request; they do not trigger a preliminary scope question. Planner has
the richer capability/source context and owns execution-related clarification.
Preflight `clarify` is limited to a future direct answer: its
`direct_answer_reason` must explain why one user choice is sufficient and no
retrieval, verification, tool or action will be needed. Without that justification,
runtime forwards the request and proposed clarification to planner.

The active role prompt is updated by migration `0182`, preserving model and
call settings. Invalid/conflicting memory focus keys from a model also route to
planner, retaining the previous focus. `user`/`tenant` identify fact owners and
never become `team.*`/`project.*` focus identities. An external project name may
remain in `task_brief.project_hints` without an entry in the memory scope catalog.

```text
user message
  -> mechanical glossary/project lookup
  -> TurnPreflight
     -> synthesizer
     -> planner -> agents -> synthesizer
     -> scoped recall -> TurnPreflight -> synthesizer
     -> clarify
  -> FactExtractor -> FactCompactor -> Reconciler
```

The mechanical lookup is code-only and bounded by ACL. It resolves only
published glossary aliases and projects so that TurnPreflight does
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

TurnPreflight may propose evidence references and user/tenant durable fact
candidates. These are hints, not writes and not proof. Glossary definitions
and project semantic memory are published only after document review. After
the final answer the fact writeback pipeline independently
validates primary user/tool evidence and runs `FactExtractor`,
`FactCompactor` and `FactReconciler`. A response may therefore say that a fact candidate
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
