# ADR: TurnPreflight Routes a User Turn Before Planning

## Status

Accepted — implemented.

## Decision

`TurnPreflight` is a system LLM role at the root of every user turn. It is a
request router and normalizer, not an agent executor and not the existing
technical `ExecutionPreflight` that prepares an already selected agent.

Factual synthesis requires sufficient input or retrieved document evidence. Requested examples and new prose use an explicit generative content mode.
TurnPreflight may search memory itself. Fresh external data, checks, actions and specialized investigation route to planner.
Chat file reads, history reads and creation of answer files can stay on the direct synthesis route. Missing
parameters and unresolved external project names are handed to planner with the
original request; they do not trigger a preliminary scope question. Planner has
the richer capability/source context and owns execution-related clarification.
Preflight `clarify` is limited to a future direct answer: its
`direct_answer_reason` must explain why one user choice is sufficient and no
retrieval, verification, tool or action will be needed. Without that justification,
runtime forwards the request and proposed clarification to planner.

The active role prompt is updated by migration `0188`, preserving model and
call settings. Invalid/conflicting memory focus keys from a model also route to
planner, retaining the previous focus. `user`/`tenant` identify fact owners and
never become document-memory scope identities. An external project name may
remain in `task_brief.project_hints` without an entry in the memory scope catalog.

TurnPreflight owns conversational interpretation: it alone receives the automatic
dialogue tail and chat snapshot. Its `TaskBrief` preserves the current objective,
conditions, resolved references with message provenance, and unresolved questions.
Downstream roles receive the exact current request and selected materials instead
of automatic history replay. `message_refs` selects historical text as task material;
`evidence_refs` selects retrieved source material. Historical assistant messages do
not establish current facts or completed actions. The complete brief is saved in
the run context and restored for planner/agent continuations. Planner can explicitly
request older history if the handoff is insufficient.

```text
user message
  -> mechanical glossary/project lookup
  -> TurnPreflight
     -> synthesizer
     -> planner -> agents -> synthesizer
     -> memory.search tool -> TurnPreflight -> synthesizer or planner
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
- `route=tool_call` with `tool_call` selecting registered `memory.search`, `file.read`, or `chat.history.read`;
  the registered tool executes and its result returns to TurnPreflight,
  which may refine the query or choose a final route;
- `route=clarify` with one question and continuation context. It reuses the
  standard `waiting_input` interaction contract but creates no plan or task.

`TaskBrief` normalizes the goal, project/entity hints, task direction,
constraints and expected result. It is not a plan. `SynthesisBrief` is the
same user-answer contract consumed by synthesizer after agent execution.
Both root roles use the same registered `memory.search` handler and
`DirectOperationExecutor` as agents. `OperationRouter` resolves the internal
execution binding without collection discovery. Arguments derive from
`HippoMemorySearchInput`, without legacy scope/fact filters. The shared corpus
follows the current access contract in [Memory](MEMORY.md).

TurnPreflight and planner choose focused queries, within `ROOT_CONTEXT_MAX_TOOL_CALLS` (default six)
followed by a final structured decision. A further tool request from preflight
hands the original task and its normalized brief to planner. Successful empty
results differ from tool failures: memory-only requests may end in synthesis
reporting no information. Preflight passages and source references reach its direct synthesis.
Planner and each agent task search independently and accumulate their own original
passages without LLM composition. Planner memory survives replans; task memory
survives retries and explicit same-executor `continuation_of` continuations.
Chat scope slugs select separate corpora, searched in parallel with one independent result group per scope. Confirmed user/tenant facts remain
separate input context.

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
  registered memory search; planning and agent work are still avoided.
- Planner is no longer the sole root routing decision-maker. It remains the
  sole producer of persisted `IterationProposal` and the owner of execution
  recovery decisions.
- Runtime trace attaches actual `tool_call`/`tool_result` events to preflight
  or planner iteration. No synthetic `memory_selector` agent or `memory_recall`
  orchestrator is created. Agent `ExecutionPreflight` events retain their meaning.

## Turn context and answer delivery (0195)

Preflight and planner use the same registered file/history/memory operations as agents.
Reading uses `DocumentExtractionService` through saved, versioned artifact representations;
it does not automatically publish chat files into shared LongMemory. Extraction algorithms
and parser selection are unchanged. Cached representations revalidate original access.

A plan-independent `runtime_run_contexts` manifest preserves the original request,
constraints, conversation references and evidence with stable IDs and role ownership.
Full snapshots live in object storage. Planner selects shared evidence for synthesis
with `SynthesisBrief.evidence_refs`; independent task/planner memory remains separate.
The run journal is never a context source.

`SynthesisBrief` declares `content_mode=grounded|generative|mixed`,
`delivery=text|files|text_and_files`, new `files` and existing `artifact_refs`.
Simple writing and example-code requests may go directly to synthesis. File answers
use a Pydantic structured response and the shared generation/writer services;
text-only answers keep streaming. A file is delivered only after successful persistence.
