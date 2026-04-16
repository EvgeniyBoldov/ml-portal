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

Not yet unified:
- shared extraction layer between chat attachments and document collection ingest.

## Contracts

### Upload policy

Resolved from platform settings:
- `chat_upload_max_bytes`
- `chat_upload_allowed_extensions`

Default intent:
- max size `50 MB`,
- allow text and office-like formats,
- block executables and unsafe content types.

### Upload flow

1. Frontend uploads file before sending the message.
2. Backend validates file and stores payload in object storage.
3. Backend creates `chat_attachment` metadata row.
4. Frontend sends `attachment_ids` with the chat message.
5. Runtime receives only validated attachment metadata and derived prompt context.

### Generated file flow

1. Assistant returns fenced file blocks.
2. Backend extracts supported file blocks.
3. Generated files are persisted as chat attachments.
4. Assistant message stores generated attachment metadata.
5. UI renders downloadable file cards/links.

Supported generated formats:
- `txt`
- `md`
- `csv`
- `tsv`
- `json`

## Delivery model

Unified file delivery works through file ids and download indirection.

Current file id contract:
- `chatatt_<attachment_uuid>`
- `ragdoc_<document_uuid>_original`
- `ragdoc_<document_uuid>_canonical`

Delivery endpoints:
- `GET /api/v1/chats/attachments/{attachment_id}/download`
- `GET /api/v1/files/{file_id}/download`

The public API returns a redirectable/presigned URL instead of exposing storage details directly.

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

## Follow-up

The remaining backend cleanup is to extract shared file inspection/parsing primitives so that:
- document collection ingest,
- chat attachment upload,
- sandbox attachment upload

depend on one reusable validation and inspection layer without coupling their orchestration flows.
