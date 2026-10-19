# Tool Entity

## Current model

A tool is an LLM-facing callable capability. Its descriptor contains a name,
description, and input schema. The capability can come from a local handler or
an active discovered provider tool.

`DiscoveredTool` stores provider discovery identity, schema, and active state.
`Tool` and `ToolRelease` can supply optional curated metadata, safety settings,
and execution defaults. They do not act as an allow-list for provider
capabilities. Collection resolution determines which provider tools are
available for a collection; runtime permissions and credentials are checked
before the tools are exposed and again along execution.

## Runtime boundary

Prompt assembly exposes tool schemas. `ResolvedOperation` is the internal
execution projection, carrying the selected provider/collection target and
policy metadata. It is not the model-facing call format. Native tool calling
uses the provider's tools protocol; plaintext fallback uses `tool_call` with a
`tool` name and arguments.

Sandbox uses the same resolution path with explicitly supported branch
overrides. It does not create a separate tool catalog or provider discovery
model.
