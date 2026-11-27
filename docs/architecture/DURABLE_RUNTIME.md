# Durable runtime for messenger integrations

An authenticated adapter admits one original request per logical run. The
portal creates a dedicated chat and preserves the original user message and
root run ID. The adapter resolves the messenger author's identity and verifies
provider events before calling the portal with credentials for the mapped user.
A replay subscription is scoped to that portal user and run.

## Lifecycle

The active segment is queued in PostgreSQL. A worker acquires a leased claim
and enters the normal chat pipeline. TurnPreflight handles initial routing and
may ask a question. A human answer returns to the saved requester. The planner
may propose `wait_until` for a durable run. The runtime validates an absolute
wake timestamp, persists the checkpoint and ends the current segment. At that
time the dispatcher queues a new segment. The continuation returns control to
the planner with the same plan and accumulated task results.

The run and its chat turn expose `queued`, `running`, `waiting_input`,
`waiting_confirmation`, `waiting_timer`, `completed`, `failed` and
`cancelled`. An expected pause ID identifies every answer or timer. Delivery
and completion use independent state. The bot can replay committed events
after a disconnect without starting a second execution.

## Adapter API

Endpoints are under `/api/v1/integrations/durable-runs` and accept Bearer
authentication. The adapter associates each incoming event with a stable
messenger event ID and records the original conversation and thread.

- `POST /api/v1/integrations/durable-runs` accepts the request text, source
  address and event ID. Persist
  the returned run ID against the thread. Retrying the same event is
  idempotent.
- `POST /{run_id}/responses` submits an answer, its event ID and the pause ID
  previously received from the event feed. Use a JSON boolean for a
  confirmation.
- `POST /{run_id}/cancel` requests cancellation.
- `GET /{run_id}/event-stream?after_sequence=0` streams committed events.
  The SSE ID is the sequence number.
- `GET /{run_id}/events?after_sequence=0` replays events, including the
  initial acknowledgement, clarification, optional sleep update and result.
  Advance the cursor only after processing all events up to it.
  A published sleep update carries `pause_id` and `wake_at`.
- `POST /{run_id}/events/{event_id}/ack` acknowledges delivery and can carry
  the message ID assigned by the messenger. Use the stable event ID as the
  provider idempotency key when available.

An admission request carries the time zone and original thread address.

```json
{
  "event_id": "mention-184",
  "text": "Проверь статус заявки завтра в 10:00",
  "timezone": "Europe/Moscow",
  "address": {
    "integration_id": "default",
    "workspace_id": "workspace-1",
    "conversation_id": "conversation-17",
    "thread_id": "thread-184",
    "source_message_id": "message-184"
  }
}
```

A response carries `event_id`, the active `pause_id` and `value`. For a
confirmation, `value: false` records a refusal. The cancellation endpoint
ends the whole run.

Set `DURABLE_RUNTIME_ENABLED=true` to accept new runs. Leave the worker
and Beat available while accepted runs are pending.

Use the provider-neutral interface with a test adapter to exercise delivery.
A deployment must configure the provider-specific identity mapping and delivery
implementation for its messenger.

## Recovery and testing

PostgreSQL owns scheduling and claim validity. The continuation envelope is
versioned and the worker validates that version before restoring it. Duplicate Celery deliveries
compete for the same segment. A later valid claim can take over after lease
expiry. Runtime task receipts and write guards determine whether already
attempted operations may be repeated. The worker rechecks user membership and
execution permissions when it resumes. Calendar sleep does not consume the
active execution budget.

See the [implementation plan](../../DURABLE_RUNTIME_PLAN.md) for migration,
rollout and the detailed verification matrix.

## Trusted assignment connectors

The `/api/v1/integrations/assignments` route accepts an authenticated
`source`, stable `event_id`, typed `user` identifiers, assignment `data`
and a separate `reply_to` connector. The portal returns `run_id` and
continues to own lifecycle, tenant, pauses and results. The existing
`durable-runs` route accepts individual user Bearer credentials.

A caller sends its `type:id` key as `X-Assignment-Connector` and an inbound
token as Bearer. Admins issue these tokens on the **Integrations** tab.
For identities without a managed record, `ASSIGNMENT_CONNECTOR_TOKENS`
provides a fallback secret map keyed by `type:id`.
A source can route output to itself by default.
`ASSIGNMENT_REPLY_ROUTES` explicitly permits other configured connectors.
Always provision distinct secrets for distinct connectors. The reply channel
can discover pending runs through `GET /deliveries`, read events for those
runs and acknowledge them. It receives the stored destination data and the
external user UUID. The source channel authenticates the original actor
for answers and cancellation. The portal stores the reply address as data.

The admin registry supports an `integration` connector for configuring an
outbound callback destination. For Clouds, enter the full URL ending in
`/api/v1/integrations/assignments/events` and attach a platform-level
Bearer credential in the connector's Credentials tab. The callback secret
authenticates requests from the portal to Clouds.
Assignment delivery currently uses the pull API described above. The
callback sender still needs to resolve the configured connector from
`reply_to` and use its endpoint and credential.
See the [connector registry](../implementation/base-functionality/INSTANCE_ENTITY.md#integration-connectors).

For a trusted Clouds source, resolution uses its stable HUID. When the
binding is absent, a verified email assertion can link one active LDAP
account with a recorded login and current tenant membership. Migration
`0218` persists the binding by connector and HUID and prevents assigning a
second HUID to the same user in that source. The tenant selected at
admission remains attached to the run. Other identifier kinds are defined
in the envelope and require their own verified resolver before use.

The [assignment router](../../apps/api/src/app/api/v1/routers/external_assignments.py)
defines the request and response surface. The human-readable connector
contract is `ASSIGNMENTS_CONTRACT.md` in the root of the Clouds repository.

The admin **Integrations** tab manages the source identity, enabled status,
reply connector and inbound Bearer tokens. Managed records take precedence
over the environment configuration for the same identity, including when
disabled. Issued tokens are hashed, bound to one integration, and scoped
to the assignment API. Migration `0220` adds their storage.

Administrators can open **Agent runs → External requests** to review admitted
assignments. The list shows the source, a preview of the request, the portal
user, the current run status and timestamps, and the run ID. It is available
through the admin endpoint `GET /api/v1/admin/agent-runs/external-requests`.
Each row opens the assignment page at `/admin/agent-runs/external-requests/:id`.
The page opens with the current run status and a timeline that starts with
the full incoming message, its sender and admission time. The same timeline
shows persisted outgoing messages, user answers, timer pauses and resumptions,
and terminal events. It displays delivery status, acknowledgment time and
delivery delay where available. Timeline offsets are measured from admission
and include any queue time and pauses. The overview uses the standard admin
block layout for the timeline and the request details. The details show the
source, timestamps and elapsed time. Active runs and runs with outstanding
deliveries refresh every 15 seconds while the page is visible.

The page reads `GET /api/v1/admin/agent-runs/external-requests/{run_id}`.
The incoming message comes from the saved request, and subsequent items come
from the durable journal. The page can render them with agent-run tracing disabled.
