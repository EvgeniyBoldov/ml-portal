# Chat contract E2E

## Admin agents E2E

`agent-admin.e2e.ts` drives the real admin UI and API through agent version
creation, contract editing, publish/current-version operations, and deletion of
an archived non-current version. It requires a refresh token for a platform
admin in a JSON file available to the frontend container:

```json
{ "refresh_token": "..." }
```

With the development stack running, run it from the frontend container:

```sh
docker compose exec -T \
  -e AGENT_E2E_AUTH_FILE=/tmp/agent-e2e-auth.json \
  -e BASE_URL=http://localhost:5173 \
  -e CHROMIUM_EXECUTABLE=/usr/bin/chromium \
  frontend npx playwright test --project=chromium e2e-tests/agent-admin.e2e.ts
```

The test creates its agent through the real admin endpoint and removes it in a
`finally` block. It is skipped when `AGENT_E2E_AUTH_FILE` is not set.

## Memory scopes and LongMemory E2E

`memory-scopes.e2e.ts` uses an authenticated platform admin and the real API to
create, edit, inspect dependencies for, and delete an isolated memory scope. It
also opens the LongMemory tab and verifies that its documents endpoint loads.
The test deletes its temporary scope through the UI and has an API cleanup
fallback. It is skipped when `MEMORY_SCOPE_E2E_AUTH_FILE` is not set.

```sh
docker compose exec -T \
  -e MEMORY_SCOPE_E2E_AUTH_FILE=/tmp/memory-scope-e2e-auth.json \
  -e BASE_URL=http://localhost:5173 \
  -e CHROMIUM_EXECUTABLE=/usr/bin/chromium \
  frontend npx playwright test --project=chromium e2e-tests/memory-scopes.e2e.ts
```

The chat contract suite drives the browser through the test Nginx proxy, the
production chat routes and services, PostgreSQL, and MinIO. Only
`RuntimePipeline.execute` is scripted. The PDF attachment scenario invokes the
real `file.read` tool and document extractor. The synthesis-file scenarios run the
real synthesizer, file writer and deterministic context finalization with only the
structured LLM result scripted. They cover download, reload, next-turn reads and
failure recovery without publishing an attachment.

## Run locally

Start the development stack first. Provide a local test user's refresh token as
JSON in `/tmp/chat-e2e-auth.json`:

```json
{ "refresh_token": "..." }
```

The frontend development container uses Alpine; install its Chromium binary
once per container with:

```sh
docker compose exec -u 0 frontend apk add --no-cache chromium
```

Start the isolated test API and Nginx listener on port 8081:

```sh
docker compose exec -d -e CHAT_CONTRACT_E2E=1 api \
  python -m uvicorn tests.e2e.chat_contract_app:app --host 0.0.0.0 --port 8011
docker compose cp apps/api/tests/e2e/nginx.conf nginx:/tmp/chat-contract-nginx.conf
docker compose exec -d nginx nginx -c /tmp/chat-contract-nginx.conf
docker compose cp /tmp/chat-e2e-auth.json frontend:/tmp/chat-e2e-auth.json
```

Run the suite inside the frontend container:

```sh
docker compose exec -T \
  -e CHAT_E2E_AUTH_FILE=/tmp/chat-e2e-auth.json \
  -e CHROMIUM_EXECUTABLE=/usr/bin/chromium \
  frontend npm run test:e2e:chat
```

The live configured-LLM attachment tests use the same local token and can be
run separately with `CHAT_E2E_LIVE=1`, `BASE_URL=http://nginx:8080`, and the
`chat-attachments` Playwright target. They verify real ingress, upload, and
message binding, then stop the model run; deterministic `chat-contract` tests
verify the extracted content and `file.read` result.

```sh
docker compose exec -T \
  -e CHAT_E2E_LIVE=1 \
  -e BASE_URL=http://nginx:8080 \
  -e CHAT_E2E_AUTH_FILE=/tmp/chat-e2e-auth.json \
  -e CHROMIUM_EXECUTABLE=/usr/bin/chromium \
  frontend npx playwright test --config playwright.chat.config.ts chat-attachments
```

After the test, stop the temporary Nginx listener with
`docker compose exec nginx nginx -s quit -c /tmp/chat-contract-nginx.conf` and
stop only the Uvicorn process running
`tests.e2e.chat_contract_app:app`.
