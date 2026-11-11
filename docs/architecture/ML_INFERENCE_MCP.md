# ML inference MCP contract

`ml-inference-mcp-shim` exposes registered ML prediction capabilities to the
Agent Runtime. It translates the MCP tool contract into calls to the ML team's
inference facade; it does not replace MLflow, Airflow, model monitoring, or deployment.

The adapter is a standalone service built from `mcp/ml_inference` using the
shared MCP server image recipe. It starts with the regular local Compose stack
and is included in the production application image manifest; it does not
require a special Compose profile. Runtime connects to it through the internal
service URL `http://ml-inference-mcp:8080/`.

The ML engineer owns training, deployment, quality monitoring, model
applicability, and the metadata exposed by the facade. The agent uses that
metadata to select a capability and treats a prediction as a bounded
statistical signal, not as an unrestricted heuristic conclusion.

## MCP tools

### `model.info`

Lists available deployed models or returns a detailed card for `model_id`.
The agent must inspect the detailed card before calling `model.predict` for an
unfamiliar model.

Input:

```json
{
  "model_id": "optional-stable-id"
}
```

The inference service returns the active deployment catalog from
`GET /v1/models` and does not implement pagination. The MCP tool therefore
does not accept or send `limit`/`cursor`. The detailed card returns the service
contract fields: `id`, `description`, `input_schema`, `output_schema`,
`input_example`, and `deployment` (`version`, `status`). Do not assume that
the service provides applicability or quality metadata unless those fields
are added to its API contract.

Example detailed result:

```json
{
  "id": "customer-default-risk",
  "object": "model",
  "created": 1787750100,
  "owned_by": "risk-team",
  "version": "17",
  "description": "Estimates the probability of default within 30 days for active loans.",
  "input_schema": {"type": "object", "required": ["loan_id"]},
  "output_schema": {"type": "object", "properties": {"default_probability": {"type": "number"}}},
  "input_example": {"loan_id": "loan-123"},
  "deployment": {"version": "17", "status": "active"}
}
```

### `model.predict`

Runs one model selected by its stable identifier. Before each prediction the
shim fetches that model's detailed card, validates `inputs` against its current
`input_schema`, then calls the facade; the facade selects the deployed version.

The MCP call arguments use `model_id` and `inputs`:

```json
{"model_id": "customer-default-risk", "inputs": {"loan_id": "loan-123"}}
```

The shim maps them to the facade request body `{"model": ..., "input": ...}`.
Pass `inputs` as the JSON value described by the model schema. If the supplied
value is a string, the shim first validates it as a string. Only when it does
not match the schema does the shim try to parse it as JSON and validate the
parsed value. This supports clients that encode an object as JSON text without
changing models whose schema accepts strings. Values must be finite JSON
values; NaN, infinity, and non-JSON Python values are rejected.

The facade response has this minimum shape:

```json
{
  "id": "resp_abc123",
  "object": "response",
  "created_at": 1787750100,
  "status": "completed",
  "model": "customer-default-risk",
  "model_version": "17",
  "output": [{"type": "prediction", "content": {"prediction": 1}}]
}
```

It may include confidence or uncertainty only when the model supports a
meaningful measure. Responses must stay within the MCP result limit; large
technical intermediates do not belong in tool output.

## Facade API used by the shim

The instance URL identifies the facade base URL. The shim calls:

- `GET /v1/models` for the active deployment catalog;
- `GET /v1/models/{model_id}` for a detailed card;
- `POST /v1/responses` with `{"model": ..., "input": ...}`.

The paths are configurable using `ML_INFERENCE_MODELS_PATH` and
`ML_INFERENCE_PREDICT_PATH`. The facade returns JSON only. Its own HTTP status
codes are authoritative for validation, authorization, availability, and
model-level errors.

Model identifiers must match the inference service contract:
`[A-Za-z0-9][A-Za-z0-9_.-]{0,254}`. The facade request's `input` field accepts
any JSON value. The inference service validates it against the deployed model's
`input_schema` and returns `SCHEMA_VALIDATION_ERROR` (HTTP 400) when it does not
conform. The MCP shim performs the same validation before prediction, using
the detailed model card fetched for that call. JSON Schema references are
resolved without network access; schemas that need unavailable external
references cannot be used for local validation.

Input validation failures return JSON-RPC error code `-32602` and a versioned
`MCPFailure` envelope in `error.data`, with category `input`, a corrective
message, the failing parameter when available, request ID, and processing
stage. Upstream HTTP failures also carry the HTTP status and a normalized
category. For recognized inference-service error codes, the shim uses static
messages and retains safe code/parameter details; it never forwards upstream
error bodies or messages, which can contain input values or internal details.
Unrecognized upstream errors retain a generic message and status. The runtime
normalizes this envelope into its standard tool failure result so the agent
can use input errors to correct a call.

## Instance and credentials

Create two remote instances using the normal connector flow:

1. A data instance (`connector_type=data`, `connector_subtype=api`) whose URL
   is the inference facade base URL. For a service on the same host, use
   `http://host.docker.internal:<published-port>`; for a service on another
   host, use its routable DNS name or IP. Keep this address in the data
   connector, not in tool code or MCP environment variables.
2. An MCP service instance (`connector_type=mcp`, `provider_kind=mcp`) whose
   URL is the MCP adapter endpoint, for example
   `http://ml-inference-mcp:8080/`.
3. Set the data instance's `access_via_instance_id` to the MCP service
   instance. Then probe/onboard the MCP provider and publish its discovered
   tools for runtime use. A collection binding is not part of this integration.

The MCP container maps `host.docker.internal` to the Docker host gateway.
The inference service remains an independent microservice; it does not need to
join the portal Compose project or share its service networks. The published
inference port must be reachable from the MCP container through a host
interface. The current inference-service Compose file publishes its port on
`127.0.0.1`, which is host-only; set its Compose interpolation variable
`INFERENCE_HOST_BIND_ADDRESS` to a host address reachable from the portal
containers (for example, the Docker host-gateway address), and restrict access
with the host firewall. This variable belongs in the inference Compose `.env`
or its launching environment, not the service container's `runtime.env`. The
data connector URL then uses `http://host.docker.internal:<published-port>`.
Alternatively, route through an existing host reverse proxy. If the service
moves to a different host, update only the data connector URL.

The adapter uses the [shared MCP authentication profiles](MCP_ADAPTER.md).
Each call requires broker credential_access by default. The broker returns the
data connector's secret and auth_type. token uses Bearer; oauth uses access_token
as Bearer; basic uses username/password; api_key uses X-API-Key. The shim never
infers a different scheme from payload fields or silently calls without auth.
Broker payloads may contain ml_inference_url/inference_url. Raw credentials
require explicit local adapter compatibility mode as documented in the shared
contract. Raw credentials are never returned by either tool.

The MCP adapter limits JSON response size. Timeouts, TLS verification and
endpoint paths are deployment configuration, not model-specific agent
arguments.

For each MCP tool call, the adapter logs the Portal correlation ID, tool,
processing stage, duration, exception class, and upstream HTTP status when
available. It does not log tool arguments, credentials, response bodies, or
raw validation payloads; error details are bounded operational summaries.
Error envelopes include the correlation ID and stage; use
`x-portal-request-id` to correlate them with the adapter container log and
runtime trace.

User credentials are added through the personal account and are bound to the
selected active remote source; the MCP adapter receives them only through the
broker flow and never exposes the stored secret in tool output.
