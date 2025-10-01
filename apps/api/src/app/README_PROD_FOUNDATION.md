This patch introduces:
- ProblemDetails-based exception handling for consistent JSON errors
- Prometheus metrics middleware and `/metrics` endpoint
- Central wiring in `main.py`

No breaking changes expected. If `prometheus_client` is not installed, add it to requirements.
