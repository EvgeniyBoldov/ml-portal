# Resolved Operation

## Purpose

`ResolvedOperation` is an internal execution contract produced after capability
resolution. It carries the selected action's name and schema together with its
collection/provider identity, policy metadata, and execution target. It is not a
separate LLM protocol.

The runtime uses the resolved contract to validate availability, apply RBAC and
credential checks, build execution bindings, and execute a requested tool.
Provider URLs, credentials, and target bindings remain internal.

## Model-facing protocol

Agents call tools. Native tool-calling providers receive tool descriptors in the
request's tools field; the plaintext fallback uses the canonical
`tool_call` shape with a `tool` name and `arguments`. The runtime maps that name
to the already resolved internal action. The LLM does not receive an
`operation`-shaped call payload.

## Resolution

`OperationRouter` combines collection/provider capability resolution,
publication metadata, execution targets, credentials, and effective
permissions. Collection-scoped calls use the public `collection_slug`; internal
instance and target identifiers are not part of the public collection contract.
