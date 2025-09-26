# Risk Register (Initial)

| ID | Risk | Impact | Likelihood | Mitigation | Owner |
|---:|------|--------|------------|------------|-------|
| R1 | Drift between code and API contract | High | Medium | Contract-first PRs; contract tests in CI | TL |
| R2 | Local HF models blow up disk/ram | High | Medium | Tiny models for tests; cache policy; heavy profile gated | MLOps |
| R3 | Duplicate handlers (routers vs controllers) | Medium | High | Routers-only rule; audit routes job | BE TL |
| R4 | SSE instability on proxy | Medium | Medium | Keep direct paths; timeouts tuned; retry/backoff | DevOps |
| R5 | Multi-tenant auth gaps | High | Low | Seed admin; RBAC tests; header + token tenant resolution | BE |
| R6 | Index corruption/TTL misconfig | Medium | Medium | ArtifactStore abstraction; e2e ingest tests | BE |
