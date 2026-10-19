# Local HippoRAG worker

Permanent development services live in the root compose file. The portal uses
the production `/portal/*` API for document-memory extraction and retrieval.
The HTTP/OpenAPI contract is at `http://localhost:8015/docs`. A JSON-RPC
MCP shim at `POST /mcp` follows the standalone SQL connector pattern.

## Production integration

`MEMORY_SEARCH_BACKEND=hipporag` is the default for API and Celery. The API selects
the registry default LLM_CHAT for native OpenIE and the EMBEDDING model selected
with `use_for_long_memory` for vectors. This selection is independent of ordinary
RAG global/tenant defaults. Provider credentials stay in the API. A temporary Redis capability
authorizes `/internal/hipporag/chat` and `/internal/hipporag/embed` callbacks and is
revoked after the operation. The worker needs access to `api:8000`; experimental
`HIPPO_LLM_*` variables do not select production models.

The existing document RAG pipeline remains intact through indexing. Its next
outbox stage (`hipporag`; old `shadow` commands redirect for compatibility) runs
`index_hipporag_document`: canonical text → native HippoRAG OpenIE/vectors/graph.
There is no typed candidate projection, extraction agent or publication/review gate.
Legacy document extraction, section-study, finalization and reconciliation jobs are
disabled. Their code and PostgreSQL data remain for history.

`memory.search` makes one parallel `/portal/corpus/search` request per selected
chat scope. Each request requires `scope_slug`; the worker selects documents
before graph retrieval and uses a separate ready index for that scope. The API
returns one independent result group per scope, including empty and failed ones.
There is no combined result or cross-scope reranking. `HIPPO_SEARCH_WORKERS`
(default 8) bounds the retrieval pool. SQLite stores documents and scope metadata;
OpenIE snapshots are shared by content and remain reusable when scopes change.
See [Memory](../../docs/architecture/MEMORY.md) for migration and result contracts.

Backfill existing RAG-indexed canonical documents with:
`docker compose exec -T api python - < scripts/index_hipporag_documents.py`.
Model selections come from the registry; graph/cache identity uses semantic
model configuration rather than mutable health timestamps. Index writes are serialized; retrieval is parallel across scope graphs.

Encoder limits come from the real sentence encoder. Chunks use a conservative
UTF-8 byte bound; long queries/facts use bounded segments with averaged, normalized
vectors, rather than silently discarding their suffix. Incomplete LLM outputs fail.
Model callbacks use a trusted `LLMCallOptions.output_token_cap` which can only
reduce the connector's allocation; user/provider `max_tokens` parameters still
cannot override that allocation. Qwen thinking settings use SDK `extra_body`.
Native HippoRAG may fall back to dense retrieval when no graph seeds survive its
fact filter. Worker failures do not silently invoke the former retriever.
Production document endpoints: `/portal/corpus/index`, `/portal/corpus/search`.
The older `/portal/extract`, `/portal/warm`, `/portal/search` remain low-level
compatibility endpoints. This is a trusted internal worker; do not expose it to
untrusted networks. The experimental MCP tools below remain separate.

```bash
docker compose build hipporag memory-experiment
docker compose up -d --no-deps hipporag memory-experiment
docker compose exec -T memory-experiment python run.py health
docker compose exec -T memory-experiment python run.py index --index fixture-v1
docker compose exec -T memory-experiment python run.py compare --index fixture-v1 --answers
```

`emb` must already be healthy when starting with `--no-deps`. A regular compose
startup starts the dependencies automatically. The client uses the existing
ignored `.long-memory-experiment/corpus/*.md` and `eval/questions.json`. SQLite
is embedded in the experiment client, not a separate database server. Raw search
hits, metadata, graph seeds, generated answers and actual answer context go to
`.long-memory-experiment/results/hipporag-http.sqlite3`. These fixtures/results
are intentionally local and are not committed. See the [experiment runner](../../scripts/memory-experiment/run.py).

## HTTP tools

- `POST /indexes`: `{index, documents: [{id, content, metadata}]}` → job ID, HTTP 202.
- `GET /jobs/{job_id}`: queued/running/succeeded/failed, graph stats or error.
- `POST /search`: `{index, query, mode: "graph" | "dense", top_k: 10}` → hits with scores/source metadata and graph seeds.
- `POST /answer`: `{index, question, hits}` → bounded Qwen answer, exact selected context, omitted hit count and token usage.
- `GET /health`: process health and configured token limits. This is not a check of upstream availability.

Index names are immutable. Submit a fresh name for a changed corpus or settings.
A failed run can be resumed with `run.py index --index fixture-v1 --retry`
(or `POST /indexes` with `retry: true`). Retry requires exactly the saved input
and compatible settings; it reuses canonical OpenIE and rebuilds derived graph
state. It cannot replace a successful index. Jobs survive restart; interrupted
jobs become failed. Search rejects
incomplete indexes. A single executor serializes indexing, searching and answering;
health/job polling remains available during work. Searches submitted during indexing
wait in the executor queue. Use one Uvicorn process; extra processes would violate
serialization and persistent job ownership.

Indexes, successful LLM response cache, input snapshots, settings and jobs.sqlite3
live in `hipporag_data`. The response cache is shared across experiment indexes,
namespaced by model and endpoint, with full request hashes as keys. Chunk identity uses content hashes; `source_refs` preserves
all origins of duplicate text. Every chunk carries document ID and character offsets.
Worker settings prevent reusing an index after model/endpoint/token settings change.

## MCP tools

`POST /mcp` supports `initialize`, `notifications/initialized`, `ping`,
`tools/list`, `tools/call`. Initialize returns `mcp-session-id`; include that header
on subsequent requests. Sessions are process-local and expire on restart. Tools:
`hipporag_index`, `hipporag_job_status`, `hipporag_search`, `hipporag_answer`. Their
input schemas are generated from the same Pydantic models as the HTTP endpoints.
This is the project-style JSON-RPC shim (protocol 2024-11-05), without SSE or
resumable streams. It is not registered in the portal tool catalog.

## Local model and limits

The defaults are Qwen3 8B Q4_K_M at `http://172.18.34.210:8081`, with
16,384 configured context tokens. The model ID is `Qwen/Qwen3-8B-GGUF:Q4_K_M`.
The embedding adapter calls the existing `emb` `/description` and `/embed/texts`
endpoints, sends at most 16 texts per request, validates each batch and normalizes vectors. No embedding model is
loaded inside HippoRAG. `all-MiniLM-L6-v2` is the existing control embedding; its
quality on Russian procedural documents must be measured separately.

Optional environment overrides in your local `.env`:
`HIPPO_LLM_BASE_URL` (llama.cpp origin, without `/v1`), `HIPPO_LLM_MODEL`,
`HIPPO_CONTEXT_TOKENS`, `HIPPO_REQUEST_TOKENS`, `HIPPO_CHUNK_TOKENS`,
`HIPPO_OUTPUT_TOKENS`, `HIPPO_PORT`.

Defaults: one OpenIE request at a time, 480-token chunks, and a 16,384-token
request budget including a 128-token safety margin. The local server was checked
through `/props` and `/slots`: it exposes four slots with 16,384 tokens per slot.
Initial output budgets are 768 for NER, 1536 for triples, 1024 for answers and the
upstream 512 for fact filtering. `HIPPO_OUTPUT_TOKENS` is the hard generation
ceiling (4096); a length-truncated response is retried with a doubled output
budget only when both this ceiling and the remaining context allow it. For Russian OpenIE, the worker serializes the named-entity list with literal
Unicode and clarifies the triple prompt to return only `{"triples": [...]}` with
explicit, nonrepeated relationships. The upstream prompt otherwise asks for both
a list and an object, and ASCII escaping inflates Cyrillic inputs. This is the
`qwen-unicode-explicit-v1` prompt profile, recorded in each index settings file;
it is a local prompt adapter, not an unmodified upstream-prompt benchmark.

The client counts the full prompt (including HippoRAG
few-shot examples) with llama.cpp `/apply-template` and `/tokenize`. Qwen thinking
is disabled via `chat_template_kwargs.enable_thinking=false`. A server exposing
those endpoints is required. Oversized prompts and outputs still truncated at the allowed ceiling fail explicitly.
OpenIE parse errors fail indexing rather than silently creating an incomplete graph.
The native HippoRAG dense fallback remains observable through empty graph seeds;
`graph_seeded=false` must not be reported as evidence of a graph benefit.

## Library isolation and evaluation

Source: [official HippoRAG repository](https://github.com/OSU-NLP-Group/HippoRAG),
pinned to commit `d5c8329422e0a0b834a15874545cb6a74b4f9b26` (2.0.0a5).
The worker uses its own virtual environment atop the project's shared ML image,
reusing Torch/numpy/scipy. Online-path dependencies are explicitly installed;
upstream's full optional/GPU dependency set is not installed. There are no imports
from `app`, no credentials resolved from the application DB, and no runtime model
downloads. Updating the shared ML base can change inherited dependency versions;
rebuild and repeat smoke checks before comparing new runs. If `emb` changes its
model behind the same URL, create a fresh index: same-dimensional model changes
are not automatically detected by this adapter.

Compare graph and dense retrieval over the **same chunks and embeddings**. Source
document recall is a diagnostic measure, not claim accuracy: the right document
may still contribute the wrong fragment. Judge answers against `gold_answers.json`,
including conditions, applicability, missing approvals and unsupported assertions.
Answer context has its own budget and can omit hits; inspect it separately from
retrieval results. The existing docs/flat/linked baseline can be compared after
checking corpus hashes and extraction completeness.

This is a trusted local experiment interface, bound to host loopback, without
portal authentication. It must not be published as a public memory API. The
application owns `memory.search` and selects indexes from the shared LongMemory
corpus by scope; LongMemory is not filtered by source ACL, user, or tenant.
Ordinary RAG collection permissions remain enforced by their own application
path. HippoRAG triples express semantic links; they do not define index scope.


## Document lifecycle and observability

The portal forks LongMemory after normalization, alongside the normal RAG
chunk/embed/index branch. Managed commands use `POST /portal/documents/add` and
`POST /portal/documents/delete` with an operation ID, document ID, generation,
selected models, and (for add) the canonical document. They return 202 immediately.
The caller retains its model capability until completion and polls
`GET /portal/operations/{operation_id}`. `GET /portal/documents/{document_id}` reads
per-document statistics without invoking models.

`portal-operations.sqlite` stores command states and document generation heads.
It uses a separate transaction from the corpus build so progress stays readable.
The worker serializes mutations in its existing single executor. Index extraction
and scope publication are reported separately. Add uses saved extraction when
available; delete rebuilds remaining scope rosters without removing shared chunks.
A newer accepted deletion fences an older in-flight add. Worker startup marks
interrupted commands failed for application recovery. Derived previous graph
generations remain on disk until separately collected.

Deployment must copy `document_operations.py`, apply API migration 0192, and update
API, Celery, frontend, and this worker together. Encoder changes use the corpus
reindex flow described above; document additions and removals use managed
document operations.

Production LLM calls have one bounded retry loop in `GatewayLLM` (SDK automatic
retries are disabled by the application adapter). `HIPPO_LLM_MAX_ATTEMPTS=3`
includes the initial call; backoff starts at `HIPPO_LLM_RETRY_BASE_SECONDS=2`
and is capped by `HIPPO_LLM_RETRY_MAX_SECONDS=30`. Retry-After is respected;
longer cooldowns are returned to durable operation recovery rather than retried
early. Invalid/empty structured output is retryable; length truncation increases
the output cap within the selected context and the 4096-token ceiling, sharing
the same attempt limit. Credentials/permission errors, unsupported contracts,
refusals, and context overflow are permanent failures. During local retries the
extraction step stays processing. Validated successes are cached; failed calls
are never cached, and partial extraction is never published. Extraction errors
propagate through native OpenIE futures with their safe cause and chunk/stage,
instead of allowing the library to replace them with a list of failed chunk IDs.
