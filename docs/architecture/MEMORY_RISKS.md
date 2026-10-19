# Memory risks and accepted decisions

> This document describes the former `MemoryItem`/`MemoryClaim` and conversational
> fact publication design. It does not describe current document LongMemory:
> LongMemory is one shared corpus for portal users, and native HippoRAG search
> does not apply user, tenant, or source ACL filters. Its scope slugs select
> indexes within that shared corpus. See [Memory](MEMORY.md).

This document records active runtime-memory risks that require operational
awareness. It is not a substitute for access control or source review.

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
- Treat tenant facts as advisory context; authoritative rules belong in
  reviewed source documents and the applicable document-memory scope.
- Monitor fact-write diagnostics and provide an administrative removal path
  for incorrect shared facts.
