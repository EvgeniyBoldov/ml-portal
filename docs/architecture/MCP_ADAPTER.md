# Shared HTTP MCP adapter

New external HTTP MCP servers are connected through a Portal-owned adapter.
Portal registers the adapter URL as its MCP connector; the data connector keeps
the destination service URL and credentials. The MCP connector has no upstream
service credentials.

`mcp/adapter/server.py` is the standalone gateway; `mcp/helpers/mcp_adapter.py`
owns the shared HTTP boundary. The Atlassian adapter uses this boundary around
its embedded upstream ASGI app. The legacy Jira and ML facade shims reuse the
shared credential resolver and authentication profiles for their REST calls.
The NetBox REST shim uses that same per-call credential resolver and token
authentication profile (`Authorization: Token …`); the shared MCP-over-MCP
gateway is not placed in front of NetBox because NetBox exposes a REST API, not
an upstream MCP server.

## Credential flow

1. Runtime resolves a credential reference from the selected data connector
   using the platform-owned operation risk: risky operations require a user
   credential; safe operations try user, tenant, then platform credentials. In
   broker mode runtime does not decrypt or carry the secret payload. There is no
   provider fallback.
2. Runtime signs a short-lived `credential_access` JWT and places it inside
   `arguments.instance_context`. The request to the adapter has no HTTP
   Authorization header; its MCP session ID is separate from credentials.
3. The adapter exchanges the JWT at the API broker on each tool call. The
   broker validates expiry, issuer/audience, data-instance ownership, credential
   activation, owner scope, and authentication type before returning the secret.
4. The adapter builds upstream authentication from the returned `auth_type` and
   the configured profile. Caller-supplied auth_type cannot override it. Missing
   fields and unsupported schemes fail rather than choosing another scheme.
5. The gateway removes `instance_context`, `credential_access`, legacy
   `credentials`, `collection_slug`, and `collection_id` from public tool args.
   Tool fields such as `url` are preserved. Runtime does not inject endpoint
   aliases or credential hints into public arguments.

Sessions hold only an opaque ID and expiry. Each upstream exchange has a fresh
client/session and the current call's authentication, including initialize. The
adapter sends `notifications/initialized`, handles JSON or bounded SSE replies,
and never replays tools/call. It supports HTTP POST MCP tools, not stdio,
legacy SSE transports, resources/prompts/subscriptions, or env-only credentials.

Discovery uses no data credentials. The upstream must expose its schema surface
without service credentials. Embedded Atlassian exposes native schemas without
source configuration or placeholder credentials; its
[broker-bound integration](ATLASSIAN_MCP_ADAPTER.md) creates the source client
only for tools/call. An upstream requiring credentials even for discovery
needs an additional discovery integration; do not store a permanent discovery
secret in adapter env.

## Profiles

| Credential auth_type | Standard | Atlassian |
| --- | --- | --- |
| token | Configured header/scheme; default Authorization: Bearer | Broker-bound native PAT client |
| basic | Basic from username/email and password/api_token | Broker-bound native Basic client |
| oauth / bearer | Bearer from access_token/token | Bearer on the broker-bound client |
| api_key | Configured header; default X-API-Key | Same explicit API-key header; upstream must support it |

Aliases choose the value within the declared scheme, never another scheme. A
Basic credential containing only a token fails. For Token-style upstreams set
`MCP_ADAPTER_TOKEN_SCHEME=Token`. The Atlassian product is selected by the tool
name (confluence_… or Jira); the data connector URL takes precedence. Generic
upstreams can receive that URL via `MCP_ADAPTER_TARGET_URL_HEADER`. Profiles
cannot make an unmodified upstream understand arbitrary credential arguments.

The embedded Atlassian adapter requires the broker in every environment.
For generic HTTP adapters, broker delivery is mandatory by default. Explicit local compatibility requires
both `MCP_ADAPTER_ALLOW_RAW_CREDENTIALS=true` and `ENV=local|dev|development`;
it accepts instance_context.credentials with an explicit auth_type. A supplied
broker context always wins, including when resolution fails. Production rejects
raw fallback.

## Tool policy

Failed calls carry a versioned `MCPFailure` diagnostic. Its canonical Pydantic
model and normalization helpers live in `apps/api/src/portal_mcp_contract`;
the API, worker and MCP images package the same source. Consumers do not
maintain an independent JSON Schema.

The diagnostic distinguishes `kind=tool|rpc|http|transport|protocol` from
`category=input|auth|access|availability|rate_limit|unknown`. It retains the
source `code`, `message`, structured `details` and JSON-RPC `rpc_code`/`rpc_data`,
plus factual `request_id`, `stage` and `http_status` when available.
Unknown failures remain unknown; an arbitrary error string is not evidence
of an authentication failure or a repair instruction.

For upstream JSON-RPC errors the normalized object is returned in `error.data`.
Tool errors retain `isError=true`, their content and structured content, and
carry the diagnostic in `result._meta["portal.failure"]`. A generic public
message does not replace the source diagnosis: source text and structured data
remain available in the normalized object. HTTP failures and initialization
failures use the same contract. Existing MCP servers without this metadata
remain supported by the API consumer's legacy normalization.

Diagnostics are bounded and secret-aware. Credential values, authentication
headers, broker tokens and secret-shaped fields are redacted before crossing
the adapter boundary; size limits produce explicit truncation markers. This
does not remove the query/parser/validation details needed to correct a call.
Sensitive structured fields use an explicit key list: diagnostic fields such
as `expected_token` and credential identifiers are not secrets solely because
their names contain `token` or `credential`. Already normalized v1 failures
retain their source category and diagnosis across another adapter hop.
The separate `user_message` is a Portal-owned safe description, not arbitrary
upstream text. Full diagnostic messages are intended for tool observations and
operator traces; they are not automatically copied into the public chat error.
The contract supplies facts and does not authorize retries or define agent
recovery policy. In particular, `tools/call` is still never replayed by the
adapter.

`MCP_ADAPTER_ENABLED_TOOLS` is an exact comma-separated allowlist. Empty exposes
no tools; `*` explicitly permits all. It filters tools/list and rejects direct
calls to hidden tools before secret resolution. Upstream cursors are preserved,
including on empty filtered pages.

`MCP_ADAPTER_TOOL_DESCRIPTORS` is a JSON object keyed by upstream tool name. It
can override title, description, and annotations, and must provide an explicit
binary risk classification for every enabled operation. The adapter strips
upstream runtime policy and publishes only its configured `safe` or `risky`
value. It does not rename tools or change input/output contracts. Example:

```json
{"model_info":{"description":"Inspect deployed model contracts","x-runtime":{"risk_level":"safe"}}}
```

There is no inferred or global default risk. An enabled operation without an
explicit descriptor is a configuration error. MCP metadata cannot select
credential ownership or override platform authorization.

## Deployment

Build with `MCP_SERVER_DIR=adapter` using the existing MCP Dockerfile. Configure
upstream, profile and allowlist before starting the optional local gateway:

```bash
docker compose --profile mcp-adapter up -d --build mcp-adapter
```

The default local port is 8019. Run one configured gateway per upstream provider.
Register `http://mcp-adapter:8080/` as the MCP connector, link the data connector
through access_via_instance_id, save credentials on that data connector, onboard
discovery, and bind the collection to the agent.

Settings: `MCP_ADAPTER_UPSTREAM_URL`, `MCP_ADAPTER_AUTH_PROFILE` (standard or
atlassian), `MCP_ADAPTER_TOKEN_HEADER`, `MCP_ADAPTER_TOKEN_SCHEME`,
`MCP_ADAPTER_API_KEY_HEADER`, `MCP_ADAPTER_TARGET_URL_HEADER`,
`MCP_ADAPTER_TIMEOUT_SECONDS` (120), `MCP_SECRET_BROKER_TIMEOUT_SECONDS` (10),
`MCP_ADAPTER_SESSION_TTL_SECONDS` (3600), `MCP_ADAPTER_MAX_REQUEST_BYTES` (262144),
`MCP_ADAPTER_MAX_RESPONSE_BYTES` (1048576), `VERIFY_SSL`, and
`MCP_ADAPTER_CA_BUNDLE`. No redirects are followed with credentials.

Every runtime MCP call uses its runtime tool-call ID as `x-portal-request-id`.
Runtime forwards it through initialize and tools/call; adapters send the same ID
to the credential broker and upstream MCP server. Search API and MCP container
logs by that value to follow one call across the boundary:

```bash
docker compose logs --since=15m api ml-inference-mcp atlassian-jira-mcp atlassian-confluence-mcp \
  | rg 'request_id=<tool-call-id>'
```

Logs record dispatch, HTTP attempts and statuses, broker resolution, selected
`auth_type`, names of authentication headers (never their values), upstream
target origin, response size, JSON-RPC code, duration, and safe transport error
details such as connection errno. They never record request/response bodies,
tool arguments, credentials, broker JWTs, prompts, model inputs, or upstream
error text. Diagnostic content travels through the bounded failure contract,
not Docker logs. Public error messages use the separate safe projection.
NetBox records the same `x-portal-request-id` through credential
resolution and NetBox REST requests. Health is available at /healthz.

Run `make test-mcp-adapter` for the focused contract suite in the API image with
the MCP sources mounted read-only. Tests live in `mcp/adapter/tests/test_adapter.py`,
`mcp/atlassian_adapter/tests/test_credentials.py`, and the backend focused broker,
runtime credential resolver, operation builder/executor, Jira and ML shim suites.
