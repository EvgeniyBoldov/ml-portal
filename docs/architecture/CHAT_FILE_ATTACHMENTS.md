# Chat File Attachments

## Purpose

Chat attachments are the canonical file surface for user chat and assistant-generated files.

The goal is simple:
- user uploads a validated file,
- runtime receives only validated attachment metadata and prompt context,
- assistant may return generated files through the same delivery model,
- download happens through one unified file-delivery contract.

## Current Scope

Implemented:
- `chat_attachments` as the storage-backed attachment entity,
- upload policy from admin settings,
- upload endpoints for chat and sandbox,
- validation by size, extension, MIME and executable blocking,
- binding uploaded attachments to user and assistant messages,
- prompt-context injection for validated attachments,
- assistant-generated files from response blocks,
- unified file delivery by attachment endpoint and by file id.

Shared inspection is provided by `DocumentExtractionService`; chat and document
collection ingest use separate profiles over the same parser pipeline. Docling
Serve is the primary converter for supported formats. Existing local extractors
remain the fallback when Docling is unavailable or cannot produce text. The
tenant-specific layout-aware PDF extractor remains the collection-ingest PDF
fallback when enabled.

## Chat artifact references

`chat_artifact_references` stores only files mentioned or returned in a chat.
Its UUID is the unified `artifact_id` passed to file tools. The row points to a
chat attachment or an external collection/template/export target; it does not
duplicate storage coordinates. Collection access is revalidated through RBAC on
every read. Removing an attachment reference removes the owned chat attachment
and storage object; removing an external reference never removes its source.

Every reference exposes a versioned, content-free artifact passport in its
metadata: origin (`user_upload`, `agent_generated`, `rag_document`, or
`external_file`), source identity/type, file name/type/size, optional bounded
description, and the latest extracted-representation ID, source fingerprint,
profile and status. Legacy JSON metadata is normalized when read. Existing
status and generated-file idempotency attributes remain available for older
consumers. Descriptions inferred by preflight are marked as model-inferred and
bound to the representation they describe. The passport never contains file
text or a text preview; content is available only through explicit `file.read`.

Role prompt builders expose these passports in `datastore.items` with
`kind=file`, alongside metadata for saved tool datasets (`kind=result`). This
inventory shares the existing artifact identity and does not copy file content
or replace artifact access checks. See [Data Workspace](RUNTIME_TOOL_RESULTS.md#model-input-inventory)
for role visibility and handoff rules. Existing extracted previews are excluded
from inventory projections, including legacy attachment contexts.

For collection RAG files, the passport identifies the source document and
collection while the artifact target remains the resolvable collection
membership. A retrieved passage/chunk is run evidence with its own provenance;
registering a file reference alone does not assert that the final answer used
that source.

[`CHAT_CONTEXT_MEMORY.md`](CHAT_CONTEXT_MEMORY.md) defines how a completed run
may add a verified artifact to this registry and separately remember its
conversational role. The context layer never replaces this registry, and its
cached metadata never grants file access.

## Contracts

### Upload policy

Resolved from platform settings:
- `chat_upload_max_bytes`
- `chat_upload_allowed_extensions`

Default intent:
- max size `50 MB`,
- allow text and office-like formats,
- block executables and unsafe content types.

Development and production Nginx accept request bodies up to `100 MB`. The
effective chat upload limit is the lower of that ingress cap and the configured
chat upload policy (default `50 MB`).

### Upload flow

1. Frontend uploads file before sending the message.
2. Backend validates file and stores payload in object storage.
3. Backend creates `chat_attachment` metadata row.
4. Frontend sends `attachment_ids` with the chat message.
5. Runtime receives only validated attachment metadata and derived prompt context.

The upload policy is exposed at `GET /api/v1/chats/uploads/policy`. Uploads use
`POST /api/v1/chats/{chat_id}/uploads` with multipart field `file`; the response
contains the chat attachment and its `artifact_id`. The message request sends
that reference in `artifact_ids`.

The API checks configured size, extension, content type, and file signature.
Oversize files return HTTP `413`; invalid or unsupported files return HTTP
`400`. The frontend uploads before submitting the message. If an upload fails,
the draft text and selected files remain available for retry. Once the chat
request is handed to the stream client, the composer clears; HTTP/SSE failures
are shown in the chat and do not put the submitted text back into the composer.
A message can also reuse a validated attachment when a user answers a
clarification; the runtime reattaches it to that continuation.

### Chat stream and continuation

`POST /api/v1/chats/{chat_id}/messages` accepts a non-empty `content` string
and optional `artifact_ids`, then returns `text/event-stream`. Public events are
`user_message`, `status`, `delta`, `pause`, `final`, `cached`, `error`, and the
terminal `done` event. `final` carries the complete answer plus `sources` and
`attachments`; clients treat it as authoritative even when they also rendered
`delta` events. A `pause` includes the `run_id`, pause `reason`, `action`,
`context`, and `contract_version`.

The chat exposes the active clarification or confirmation in its header and
restores it from `GET /api/v1/chats/{chat_id}/paused-run`. A continuation uses
`POST /api/v1/chats/runs/{run_id}/resume` and returns the same SSE event stream.
Responses use `{ "action": "answer", "response": "...", "pause_id": "..." }`;
a confirmation uses a JSON boolean in the same field. The server validates the
response against the saved interaction schema and rejects stale IDs with HTTP
`409`. An answer resumes the component that asked, preserving the same root
turn and available attachments. Cancellation is a separate `action="cancel"`.
See [Runtime Interactions](./RUNTIME_INTERACTIONS.md).
Stopping the stream aborts the request and marks its turn cancelled.

On stream errors, the server emits a safe `error` event when the stream is
already open. HTTP errors before the stream opens keep their HTTP status and
detail. The frontend displays a recoverable error; a submitted message is not restored
to the composer. It stops consuming events after the first terminal event so stale events
cannot replace a newer pause or completed response.

### Generated file flow

1. Agents may create execution artifacts with `file.generate`; synthesis may create answer files.
2. For new answer files, synthesis returns a validated structured message plus file bodies.
3. `FileGenerationService` and `ArtifactWriter` serialize and register real files.
4. The assistant message, delivery references and deterministic chat context are finalized before the external `final` event.
5. UI renders the existing downloadable file cards. Fenced code blocks alone do not create files.

Supported generated formats are taken from `FileCodecRegistry`: `txt`, `md`, `py`,
`json`, `csv`, `docx`. Each file retains the existing size limit; synthesis accepts
up to `SYNTHESIS_MAX_FILES` files (default eight). Failed mandatory files prevent a
successful final response. Generation is idempotent by root run and deliverable slot.
Reusing a file does not reassign its original owning message.

### Saved extracted representations

`chat_artifact_representations` links an internal representation to the original
`artifact_id`, source SHA-256 and extraction profile/version. Content lives in object
storage, and metadata records parser, warnings and completeness. The representation
has no separate user-visible attachment card. Explicit `file.read` calls reuse it
across roles and turns after checking source access and version. Limited extraction
remains partial; cached representation status never substitutes for reading its
content or proves complete analysis.

Turn preparation loads passports and representation status without reading the
stored representation object or invoking extraction. Files are read explicitly
through `file.read`. Chat context stores only references, read status and a
bounded model-inferred description.
Chat uploads are not automatically indexed by HippoRAG or published into shared memory.
Explicit private indexing and document-local paged reads/search are available
through [file.data.*](FILE_DATA.md), independently of shared document memory.

Internal objects abandoned by transaction rollback and obsolete run snapshots are
collected by the existing orphan-cleanup worker after its grace period. Original
source access remains authoritative even when an extracted representation exists.

## Delivery model

Unified file delivery works through file ids and download indirection.

Current file id contract:
- `chatatt_<attachment_uuid>`
- `ragdoc_<document_uuid>_original`
- `ragdoc_<document_uuid>_canonical`

New tool-facing contract: `artifact_id` (UUID of a chat artifact reference).
The legacy file ids remain available to download endpoints while existing
transport consumers are migrated.

Delivery endpoints:
- `GET /api/v1/chats/attachments/{attachment_id}/download`
- `GET /api/v1/files/{file_id}/download`

The public API returns a backend download endpoint (`/api/v1/files/{file_id}/download`) and streams the file through the backend proxy without exposing direct MinIO/S3 URLs.

Deprecation note:
- direct object-storage links in message metadata (`url`, presigned S3/MinIO URLs) are deprecated;
- canonical metadata fields are `file_id` and `download_url`;
- legacy `url` values are supported only as a backward-compatibility fallback for previously persisted messages.

Detached artifact rule:
- The current `ArtifactWriter` requires a chat and owner for generated artifacts.
- When chat context exists, the same artifact may be linked to that chat for UX continuity.
- Chat-scoped listing remains chat-scoped; detached artifacts are delivered by `file_id` or `storage_uri`.

## Runtime rule

Runtime must not consume raw uploaded bytes directly from the chat request.

Runtime sees:
- attachment metadata,
- validated ownership and tenant binding,
- derived prompt context,
- generated file references in assistant output.

This keeps chat execution and storage concerns separated.

## Sandbox rule

Sandbox uses the same attachment model and validation policy as chat.
It is not a second file subsystem.

The only difference is the execution surface:
- chat attachments feed normal chat runtime,
- sandbox attachments feed sandbox session runs.
