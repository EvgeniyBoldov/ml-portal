# ML inference MCP contract

`ml-inference-mcp-shim` exposes registered ML prediction capabilities to the
Agent Runtime. It translates the MCP tool contract into calls to the ML team's
inference facade; it does not replace MLflow, Airflow, model monitoring, or deployment.

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
  "model_id": "optional-stable-id",
  "limit": 20,
  "cursor": "optional-opaque-cursor"
}
```

The detailed facade response must include a stable `id`, the prediction
purpose and applicability, `input_schema`, output semantics, a deployed
version/alias, quality metadata, and warnings or non-applicability limits.
Catalog results are paginated and must not expose an unbounded registry dump.

Example detailed result:

```json
{
  "id": "customer-default-risk",
  "display_name": "Customer default risk",
  "description": "Estimates the probability of default within 30 days for active loans.",
  "applicability": {
    "applies_when": ["active loan", "30-day horizon"],
    "does_not_apply_when": ["missing verified income"]
  },
  "input_schema": {"type": "object", "required": ["loan_id"]},
  "output_schema": {"type": "object", "properties": {"default_probability": {"type": "number"}}},
  "deployment": {"version": "17", "alias": "production", "trained_at": "2026-08-01T00:00:00Z"},
  "quality": {"metric": "roc_auc", "value": 0.84, "evaluated_at": "2026-08-10T00:00:00Z"}
}
```

### `model.predict`

Runs one model selected by its stable identifier. `inputs` must conform to the
schema returned by `model.info`; the facade selects the deployed version.

```json
{
  "model": "customer-default-risk",
  "input": {"loan_id": "loan-123"}
}
```

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

## Facade API expected by the shim

The instance URL identifies the facade base URL. The shim calls:

- `GET /v1/models?limit=<n>&cursor=<opaque>` for the catalog;
- `GET /v1/models/{model_id}` for a detailed card;
- `POST /v1/responses` with `{"model": ..., "input": ...}`.

The paths are configurable using `ML_INFERENCE_MODELS_PATH` and
`ML_INFERENCE_PREDICT_PATH`. The facade returns JSON only. Its own HTTP status
codes are authoritative for validation, authorization, availability, and
model-level errors.

For schema validation failures, the facade error fields (`message`, `type`,
`param`, and `code`) are the source of truth; the shim must not add secrets,
request payloads, or provider internals to the MCP result.

## Instance and credentials

Create an ML inference MCP tool instance whose data-instance URL is the facade
base URL. The adapter uses the existing broker-first MCP credential flow. A
broker payload may contain `ml_inference_url`/`inference_url` and one of
`token`, `api_token`, `access_token`, or `api_key`; the token is forwarded as a
Bearer credential. A network- or mTLS-protected facade may intentionally use
no bearer token. Raw credentials are never returned by either tool.

The MCP adapter limits catalog page size and JSON response size. These limits,
timeouts, TLS verification and endpoint paths are deployment configuration,
not model-specific agent arguments.

User credentials are added through the personal account and are bound to the
selected active remote source; the MCP adapter receives them only through the
broker flow and never exposes the stored secret in tool output.
