# File Delivery Proxy Plan

## Goals
- Do not expose MinIO/S3 URLs to clients.
- Provide downloads only to authenticated users with tenant/resource checks.
- Use unified `file_id` contract across chat, RAG, generated files, and CSV exports.
- Implement async CSV export with S3 TTL of 2 hours.

## Checklist
- [x] Define unified response contract for internal files (`file_id`, `download_url`, `file_name`, `content_type`, `size_bytes`, optional `expires_at`).
- [x] Keep public download entrypoint as `GET /api/v1/files/{file_id}/download`.
- [x] Convert file download endpoint to backend proxy stream (no redirect to S3).
- [x] Extend `FileDeliveryService` resolver for all required file kinds (`chatatt`, `ragdoc original/canonical`, export files).
- [x] Enforce access checks in resolver for authenticated user + tenant boundaries.
- [x] Remove direct presigned URL from RAG download endpoints and return backend link contract only.
- [x] Remove direct presigned URL from collection document download endpoint and return backend link contract only.
- [x] Update chat attachment download API contract to return backend file link contract only.
- [x] Update structured answer file block generation to use `file_id/download_url` instead of raw `url`.
- [x] Update chat frontend file actions to always use backend `download_url` or `file_id` and never open internal `url` directly.
- [x] Update RAG sources/status modal frontend flows to use backend file links only.
- [x] Add async CSV export pipeline: request -> background job -> artifact in S3.
- [x] Add export artifact `file_id` support and resolver branch in `FileDeliveryService`.
- [x] Enforce export artifact TTL 2 hours in storage cleanup/lifecycle and expiration checks.
- [x] Add/adjust backend tests for resolver access, proxy streaming behavior, and no-MinIO URL responses.
- [ ] Add/adjust frontend tests for file download link behavior in chat and RAG UI.
- [ ] Add migration/compatibility handling for old messages where attachment metadata may contain `url`.
- [ ] Document final API contract and deprecation of direct S3 URLs.

## Status
- [x] Plan recorded in repository.
- [x] Implementation in progress.
