# Agent Entity

## Purpose

An `Agent` is a versioned execution persona. Its published version defines
prompt content, execution settings, safety constraints, and permitted data
collections. The runtime invokes the agent for a planner-assigned task or an
explicit supported API flow.

## Runtime inputs

Before execution, runtime resolves the agent version, effective policy,
permitted collections, available tools, credentials, and collection/provider
targets. The agent receives task-relevant context and the callable tools exposed
for that execution. Raw provider records, credentials, and execution bindings
remain internal.

## Tool protocol

Agent calls use the model provider's native tool-calling protocol when
available, with a plaintext `tool_call` protocol fallback. Both name a tool and
provide arguments. Runtime validates the call against the resolved tool set,
applies permission/policy checks, then dispatches it to the internal execution
binding.

Agent versions retain their publish lifecycle and can narrow collection access.
They do not replace runtime RBAC, credential resolution, or execution policy.
