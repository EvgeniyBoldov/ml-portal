# Discovery Entity

## Purpose

`Discovery` scans capability sources and stores raw executable artifacts.

Its only question is:
"what capabilities currently exist in connected local and remote providers?"

## Output

Discovery produces `DiscoveredTool`.

`DiscoveredTool` is a raw capability snapshot with:
- `slug`, `name`, `description`
- `source`
- `provider_instance_id`
- `input_schema`, `output_schema`
- domain or context hints from source
- lifecycle state (`is_active`, `last_seen_at`)

This is not a published runtime tool and not a semantic release.
`ToolResolver` consumes this raw artifact together with `ToolRelease` to build the agent-facing tool view.

## Sources

Discovery currently ingests:
- local registry handlers,
- remote MCP provider capabilities.

Both are normalized into the same raw artifact type.

## Responsibilities

Discovery is responsible for:
- scanning sources,
- upserting `DiscoveredTool`,
- preserving source provenance,
- tracking appearance/disappearance over time,
- refreshing raw contracts.

Discovery is not responsible for:
- creating `Tool`,
- curating runtime semantics,
- publishing planner vocabulary,
- deciding whether a capability is agent-visible.

## Relation To Tool Publication

`DiscoveredTool` is the input to publication, not the publication result.

Possible states:
1. capability exists only as `DiscoveredTool`
2. capability is reviewed in sandbox as draft candidate
3. capability is linked to a `Tool`
4. capability is represented in runtime through effective `ToolRelease`

Important rule:
- not every discovered capability must be published,
- discovery inventory is intentionally broader than runtime vocabulary.

## Relation To Sandbox

Sandbox may treat unpublished `DiscoveredTool` as a draft publication candidate.

This does not mutate global admin publication state.
It only creates an effective branch-local view through resolver overlays.
