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

Runs one model selected by its stable identifier. `inputs` must conform to the
schema returned by `model.info`; the facade selects the deployed version.

The MCP call arguments use `model_id` and `inputs`:

```json
{"model_id": "customer-default-risk", "inputs": {"loan_id": "loan-123"}}
```

The shim maps them to the facade request body `{"model": ..., "input": ...}`.

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
`[A-Za-z0-9][A-Za-z0-9_.-]{0,254}`. The `input` value is arbitrary JSON and
must conform to the selected model's `input_schema`; the MCP adapter preserves
objects, arrays, strings, numbers, booleans, and null without coercion.

For schema validation failures, the facade error fields (`message`, `type`,
`param`, and `code`) are authoritative. The shim returns a generic MCP error
without leaking credentials, request payloads, or provider internals.

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

The adapter uses the existing broker-first MCP credential flow. A
broker payload may contain `ml_inference_url`/`inference_url` and one of
`token`, `api_token`, `access_token`, or `api_key`; the token is forwarded as a
Bearer credential. A network- or mTLS-protected facade may intentionally use
no bearer token. Raw credentials are never returned by either tool.

The MCP adapter limits JSON response size. Timeouts, TLS verification and
endpoint paths are deployment configuration, not model-specific agent
arguments.

User credentials are added through the personal account and are bound to the
selected active remote source; the MCP adapter receives them only through the
broker flow and never exposes the stored secret in tool output.
