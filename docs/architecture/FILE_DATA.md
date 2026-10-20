# Document-local file data tools

`file.data.*` operates on one authorized chat `artifact_id`, regardless of whether
the file was uploaded, generated or referenced from a document collection.
`collection.document.search` retains its collection-wide semantics. File indexes
are opt-in, private derived data; creating one does not publish a document into
the shared LongMemory corpus or add it to an ordinary RAG collection.

## Operations

All tool schemas come from `schemas/file_data.py` Pydantic models. Builtins are
registered in `agents/builtins/file_data.py` and published through normal startup
sync, system capability resolution and effective permissions.

* `file.data.read(artifact_id, offset=0, limit=10000, representation_id?)` reads a
  page of canonical extracted text. It returns `next_offset`, `total_chars`,
  `read_complete`, `source_complete`, source fingerprint and representation ID.
  Pass the representation ID on subsequent pages; a source/version change fails
  explicitly rather than mixing document versions. The configured
  `CHAT_FILE_READ_MAX_CHARS` also caps each page. Empty/unreadable or partial
  extraction remains explicit. `file.read` retains its existing bounded-preview
  contract.
* `file.data.prepare(artifact_id, backend=vector|longmemory)` explicitly prepares
  a complete document-local index. A partial extraction or empty document cannot
  produce a ready index. `vector` uses the first selected RAG embedding model,
  bounded embedding inputs and a private Qdrant collection. `longmemory` uses the
  existing LongMemory model selection/capability gateway to build a private
  document graph. Preparation reuses an existing index only after checking its
  source version, expiry, encoder/model identity and actual document chunk count.
* `file.data.search(artifact_id, query, backend=auto|vector|longmemory, limit=5)`
  searches a prepared index for that exact document. `auto` tries a current
  vector index first, then a current LongMemory index. It does not build an index,
  extract missing text or fall back to a shared corpus. Results contain exact
  canonical-text character spans, chunk IDs, scores and representation identity.
  Source metadata carries these references through task results and synthesis.
  Responses are bounded explicitly with `response_truncated`; truncating the
  first oversized hit is marked on that hit as well.

Preflight and planner can resolve read/search through their existing contextual
tool executor, subject to effective permissions. Preparation is an agent
capability. File-data tools return `direct` results rather than creating SQL
datasets. They bypass in-turn tool-result reuse so source access, revision and
temporary-index readiness are checked again on each call.

## Missing indexes versus no matches

| Condition | Tool result |
| --- | --- |
| No prepared index/current canonical representation | Failure, `document_not_indexed` |
| Expired index, changed source or model | Failure, `document_not_indexed` |
| Missing Qdrant collection or zero/incomplete document chunks | Failure, `document_not_indexed` |
| Missing private LongMemory scope/ready marker or document chunks | Failure, `document_not_indexed` |
| Backend/network/model service failure | Failure, not an empty successful search |
| Ready, verified index; retrieval yields no matches | Success, `status=ready`, `hits=[]` |
| Revoked file/source access or unavailable sandbox artifact | Failure, `artifact_unavailable` |

The user-facing missing-index message says the document is not vectorized for
the selected backend and suggests explicit preparation. The root executor
preserves that error code and message for the model. It must not infer that the
document contains no relevant information.

Qdrant checks filter by private namespace, artifact ID, representation and source
fingerprint. The native query path intentionally does not use the shared
adapter's missing-collection-to-empty-list behavior; chunk presence is checked
before and after retrieval. LongMemory verifies the exact private graph identity,
namespace, ready/expiry marker and actual document vectors before retrieval.
Loading a private graph for search cannot run indexing or extraction.

## Storage and lifecycle

Canonical representations reuse `chat_artifact_representations` and S3. Their
`file_data` extraction profile uses the shared extraction service's complete
`rag_ingest` mode, separate from a bounded chat preview. Oversized output fails;
it is never silently indexed as a complete document.

Private index bindings live in `chat_artifact_references.metadata_snapshot.file_data`.
Only status, representation/source identity, count and expiry are projected in
artifact passports and `datastore.items[].data_indexes`; internal collection
addresses, model bindings and graph coordinates are not prompt inventory fields.
No new persistence table or database migration is needed for file data itself.

Qdrant collection identities include expiry, document/namespace/version and the
encoder fingerprint. Private LongMemory graphs include chat/artifact namespace,
document version and model identity. They do not create shared-corpus scope rows.
Native worker extraction/embedding/LLM caches retain their existing cache policy.

Index access expires after `FILE_DATA_INDEX_TTL_SECONDS`. The independent hourly
`cleanup_expired_file_data_indexes` task removes expired private Qdrant collections
and private LongMemory graphs/snapshots, including abandoned preparations. File
reference deletion removes its current derived indexes; removing an external
reference never deletes its source document or source collection. Older derived
index versions are collected by expiry. Chat deletion can leave derived indexes
until that cleanup; source authorization is still required during that interval.

Existing collection/shared-memory indexes are not automatically adopted as
private file indexes. Explicit preparation keeps file search restricted to that
document and avoids post-filtering corpus-wide top-k results.

Deploy the API/worker and updated LongMemory worker together; private file
endpoints are implemented under `/portal/files/*`. Configuration defaults are
documented in [Environment](../admin/ENV.md#chat-file-context).
