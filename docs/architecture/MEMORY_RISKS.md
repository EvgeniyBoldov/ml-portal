# Memory risks and accepted decisions

This document records deliberate runtime-memory trade-offs that require
operational awareness. It is not a substitute for access control or for the
source-backed project-memory pipeline.

For the current memory surfaces and document publication flow, see
[`MEMORY.md`](MEMORY.md).

## Accepted risk: conversational tenant facts

`FactExtractor` can classify evidence from a user message as `scope=tenant`.
`FactReconciler` publishes such a fact only after independent observations,
but an ordinary tenant member can create those observations over multiple
turns. A confirmed tenant fact is then available to other members of the same
tenant.

We accept this risk for the current internal-collaboration product because
tenant memory is treated as a shared working convention layer, not an
authoritative policy store. The runtime does not use these facts to grant
permissions, resolve credentials, execute privileged operations, or bypass
tool RBAC.

Operational controls:

- Do not store security policy, access rights, credentials, or approval state
  in conversational tenant facts.
- Treat tenant facts as advisory context; authoritative departmental rules
  belong in source-backed documents and project `MemoryItem` records.
- Monitor fact-write diagnostics and provide an administrative removal path
  for incorrect shared facts.
- Revisit this decision before exposing tenant memory to an untrusted or
  externally managed user population. That change requires trusted-source or
  RBAC-gated publication for `scope=tenant`.

## Open design gap: user-contributed project rules

There are two project-memory sources:

1. Documents produce source-backed `MemoryItem` records through the document
   ingestion pipeline.
2. A user may state a durable project rule during a chat.

The second path is not implemented by the current fact writeback contract:
`FactScope` only supports `user` and `tenant`, and the extractor transport has
no resolved `project_id` or `project_key`. Prompts that request
`scope=project` therefore produce candidates rejected by runtime validation.

Do not route these candidates into tenant facts as a workaround. A future
project-rule write path must resolve the project through the catalog, carry a
project identifier and evidence provenance, enforce project-level write
authorization, and persist a source-backed `MemoryItem` (or an explicitly
designed equivalent) with an appropriate review/confirmation lifecycle.
