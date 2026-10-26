# ADR: RootRoutePolicy Recommends; TurnPreflight Decides

## Status

Accepted — implemented in backend runtime, prompt contract and trace journal.

This decision supersedes the direct-handoff behavior in
[`ADR_TURN_PREFLIGHT_ROUTING.md`](ADR_TURN_PREFLIGHT_ROUTING.md).

## Context

`RootRoutePolicy` currently evaluates the current request and the RBAC-filtered
agent catalog before `TurnPreflight`. A match can bypass TurnPreflight and
construct a `TaskBrief` directly for planner. The policy is therefore a
second terminal router, despite its deterministic lexical rules having less
conversational context than TurnPreflight.

Run `e7ca9266-bfd3-4aee-b777-ba8081f6bbdd` shows the consequence. For
«посмотри в инвентори какие у меня есть коммутаторы», policy events 3–5
matched `live_netbox_inventory_lookup`; the next event was planner start.
There was no `turn_preflight` entity. In the earlier run
`e4701915-824d-4b02-aaa9-295b50233323`, TurnPreflight proposed `clarify` and
runtime later rerouted to planner. The two paths give different authorities
over the same routing decision, and the policy path cannot interpret a short
follow-up such as «А в инвентори посмотри» against the preceding dialogue.

The policy must remain a cheap, bounded signal layer. It can recognize likely
intent and available source candidates; it cannot establish the user's full
goal, decide that clarification is unnecessary, or launch planning. The
existing invariant that root routing precedes planning remains: TurnPreflight
is the only final root router before planner/synthesizer.

## Decision

For every new implicit chat turn, evaluate `RootRoutePolicy` and record its
recommendation, then invoke `TurnPreflight` regardless of whether a rule
matched. `TurnPreflight` receives the recommendation alongside the same
conversation and execution context it already uses and returns the final
`TurnPreflightDecision`.

The recommendation is advisory. A match may guide TurnPreflight toward
`planner` and identify an allowed source candidate; an unmatched result means
there is no policy hint. Neither result completes routing or skips preflight.
TurnPreflight may accept, modify, or reject a recommendation based on the
current request, dialogue, continuation state, tools and available agents.
It remains responsible for the final route and corresponding typed brief.

Typed answers to a saved planner/agent interaction remain on the existing
resume path: they resume the saved requester checkpoint rather than starting
a fresh root route. New user turns, including elliptical follow-ups, run the
policy and TurnPreflight path.

## Recommendation contract

Use a Pydantic contract, not an untyped dictionary. The policy input contains:

- `current_user_query`: the exact current user message;
- `effective_goal`: the saved goal when one exists, otherwise the current
  request;
- `recent_dialogue`: the same bounded, role-labeled, provenance-bearing
  dialogue projection supplied to TurnPreflight;
- `continuation`: validated continuation metadata already assembled by the
  runtime, excluding journal replay;
- `available_agents`: the existing RBAC-filtered catalog, with no unfiltered
  candidate list or credentials.

The policy does not receive raw runtime journal history, secrets, or access
outside the already resolved agent catalog. It may consume the shared
mechanical lookup only if a future rule requires it; do not duplicate the
lookup or use it to assert live source facts.

The output is a `RootRouteRecommendation` with these fields:

| Field | Contract |
| --- | --- |
| `status` | `matched` or `unmatched`; says whether a rule recognized a useful signal, not whether a route was selected. |
| `recommendation_id` | Stable ID for this policy decision within the run; used to join the policy trace to TurnPreflight. |
| `rule_id` | Stable rule identifier on a match; null when unmatched. |
| `route_hint` | Optional `planner`, `synthesis`, or `tool_call`; null when unmatched. It is never an effective route. |
| `source_agent_hint` | Optional slug only when it exists in `available_agents`; a hint, not an assignment. |
| `signals` | Bounded machine-readable signal names; no copied prompt or full user text. |
| `reason_code` | Stable code, e.g. `likely_live_inventory_lookup`, `no_matching_rule`, or `source_not_available`. |
| `summary` | Short operator/model-facing explanation of the recommendation and its limits. |

Do not include `effective_route` in this contract. Do not infer that a source
is available from lexical matching; source hints must be drawn from the
RBAC-filtered catalog. If a rule recognizes a likely live-data request but no
matching allowed agent exists, return a useful recommendation with
`source_agent_hint=null` and `reason_code=source_not_available`, or return
unmatched when the policy has no safe hint. TurnPreflight still decides how to
proceed using its full available tool/agent context; it must not fabricate an
agent or promise retrieval.

For `matched` and `unmatched`, the ordinary root turn continues through
TurnPreflight. An unmatched result is not a planner fallback and must not
change the input route. A matched recommendation is a prompt hint; it can be
rejected when recent dialogue shows a documentation question, a different
referent, an already answered question, or another sufficient direct-answer
path. Clarification remains valid only under the existing direct-answer rule:
one user choice is sufficient and no retrieval, verification, tool, or action
will be needed.

## Context and elliptical follow-ups

The policy and TurnPreflight must see the current message as well as the
conversation needed to resolve it. In particular, for
«А в инвентори посмотри», TurnPreflight receives:

1. the exact current message;
2. `effective_goal` and saved `active_goal`/continuation references when
   available;
3. the bounded `recent_dialogue` in chronological order, including message
   IDs and roles;
4. the recommendation and its `recommendation_id`;
5. the ordinary TurnPreflight context: chat snapshot, selected artifacts,
   mechanical lookup, facts/project context, allowed tools and agents, and
   continuation metadata.

TurnPreflight resolves the fragment against that context and writes a
self-contained `TaskBrief` or `SynthesisBrief` with provenance-bearing
`resolved_references`. It preserves prior objective constraints that remain
relevant. A policy recommendation alone never supplies missing goal details
and never authorizes replaying historical assistant claims as current facts.
The runtime journal remains observability data, not conversational context.

## Trace contract and event order

`route_policy` remains a trace entity, a direct child of `run`. It is a
recommendation lifecycle, not a second router. For a new implicit turn the
expected order is:

```text
run_start
route_policy_start
route_policy_decision
route_policy_end
turn_preflight orchestrator_start
TurnPreflight LLM request/response (possibly memory tool loop)
preflight_route_decision
planner | synthesizer | clarify interaction
```

Both a match and no match emit the policy lifecycle, then start TurnPreflight.
The policy entity ends before the TurnPreflight entity begins. Directly
selected-agent runs and saved checkpoint resumes may omit this sequence and
must state their existing path in the run trace.

Recommended event fields:

- `route_policy_start`: `recommendation_id`, `current_user_query` length/hash
  or the existing redacted request representation, `effective_goal` length,
  `dialogue_message_count`, and `context_truncated` flags. Do not copy the
  full dialogue into trace payloads.
- `route_policy_decision`: all output contract fields; no `route` field with
  planner/TurnPreflight as a supposed destination.
- `route_policy_end`: terminal status and duration.
- TurnPreflight `llm_request` context snapshot: compact recommendation,
  `recommendation_id`, and `recent_dialogue` provenance as currently
  represented by its ordinary prompt snapshot.
- `preflight_route_decision`: `proposed_route` (the model's route),
  `effective_route` (the final validated TurnPreflight route),
  `policy_recommendation_id`, `policy_disposition` (`accepted`, `modified`,
  `rejected`, or `not_applicable`), and `reason_code`/detail. The effective
  route is always the validated TurnPreflight decision for this path.

The frontend must display the policy result as “recommendation” and the
TurnPreflight result as “final route”. It must not render a policy match as a
completed route or infer a route from event order. Historical events with the
legacy `route_policy_decision.route` remain readable as legacy records.

## Implementation record

1. `RootRouteRecommendation` is a typed Pydantic contract with no effective
   route field. The bounded rule produces a planner hint and, only when
   RBAC-filtered availability confirms it, a source-agent hint.
2. Every new implicit turn starts TurnPreflight after the policy entity ends.
   The policy no longer constructs `TaskBrief` or skips the preflight call.
3. TurnPreflight receives the typed recommendation, effective goal, existing
   continuation and the same bounded, provenance-bearing dialogue used for
   reference resolution. Its prompt marks the recommendation advisory.
4. Policy trace events contain query length/hash, goal length, dialogue count
   and truncation status, not copied dialogue. `preflight_route_decision`
   carries recommendation linkage, disposition and reason code.
5. Updated docs describe the recommendation flow. Historical events using the
   legacy `route_policy_decision.route` shape remain readable by trace clients.
6. Migration `0205` updates only the active TurnPreflight rules prompt;
   operator-selected model and execution settings remain unchanged.

## Acceptance criteria

- A matched policy recommendation never skips TurnPreflight or creates a
  planner brief itself.
- An unmatched policy result also reaches TurnPreflight; absence of a match
  does not force planner or clarify.
- TurnPreflight is the sole producer of the effective root route and its
  matching typed brief.
- For an allowed live-inventory request, a matched recommendation is visible
  in the TurnPreflight input, and TurnPreflight can select planner without an
  extra clarification asking which available source to use.
- For an unavailable source, policy output contains no unauthorized agent
  slug; TurnPreflight chooses an honest route/limitation from available
  capabilities.
- For a dialogue sequence ending in «А в инвентори посмотри», TurnPreflight
  receives the earlier user request and relevant assistant response with
  message provenance, resolves the referent, and preserves the earlier goal
  in its handoff. It does not ask the user to repeat context already present.
- A prior documentation/process question about inventory does not become a
  forced planner task solely due to keyword overlap; the recommendation can
  be rejected using dialogue and intent.
- Trace ordering and parent links match the sequence above for both matched
  and unmatched policy results. `preflight_route_decision` distinguishes the
  model route from the final effective route and records policy disposition.
- Trace UI labels recommendations and final routes distinctly and reads
  pre-migration journals without fabricating a TurnPreflight node.
- Focused backend routing/trace tests, frontend trace projection tests, and
  corresponding type/lint checks pass; architecture docs are reconciled only
  after implementation.

## Risks

- Passing dialogue into a larger preflight prompt can increase tokens. Reuse
  the existing bounded projection and do not attach extra unbounded history.
- A strong recommendation can still bias the model. The prompt and evaluation
  cases must explicitly test rejection, especially documentation requests and
  ambiguous sources.
- A lexical rule may match the follow-up without understanding its referent.
  This is acceptable only because the rule is advisory and TurnPreflight sees
  the dialogue.
- Keeping old and new trace shapes requires a frontend compatibility path;
  distinguish missing legacy fields from a real unmatched recommendation.
- More LLM routing calls can affect latency and budget. Measure this against
  the avoided false direct handoffs; do not reintroduce a bypass as an
  unreviewed optimization.
