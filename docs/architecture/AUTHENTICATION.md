# Authentication and browser sessions

## Bearer credentials

The API accepts JWT access tokens and personal API tokens through the
`Authorization: Bearer` header. Browser API requests may also use the
httpOnly `access_token` cookie; machine endpoints such as MCP and shadow invoke
require the header. Refresh tokens are accepted only by `/auth/refresh` from
the httpOnly `refresh_token` cookie.

JWTs establish identity. Each request reloads the active user and membership
assignments from PostgreSQL; authorization does not trust role or tenant claims
embedded in an access token. `Users.is_admin` grants platform admin access.
Tenant administrator and data editor flags belong to the user's tenant
membership and do not grant access to the platform admin application. Browser access tokens include a refresh
session family id and are rejected once that family is revoked.

## Refresh-token lifecycle

Every browser login creates a persisted refresh-session family. Refresh tokens
are one-use: rotation consumes the presented token and stores its successor in
the same family. Reuse of a consumed token revokes the remaining family, which
also invalidates its access tokens. Logout revokes the family and clears the
browser cookies. Expired session rows are removed as new sessions are issued.

The `auth_refresh_sessions` table is created by migration `0199`. After that
migration, browser sessions issued before the refresh-family change must log in
again to obtain a tracked refresh token.

## Personal API tokens

PATs resolve their current owner, platform admin status, tenant roles and active
tenant memberships from the database. `PAT_ENABLED=false` blocks both new token creation and authentication
of existing PATs; listing and deleting stored tokens remain available so users
can inspect or revoke them.

## Configuration and operational routes

The application defaults to `ENV=production` and `DEBUG=false`. Local
development must explicitly set `ENV=local` or `ENV=development`. Other
environments require a non-default JWT secret of at least 32 characters.
Production cannot start with debug mode enabled.

Detailed monitoring and both Prometheus endpoints require an admin Bearer
credential. The simple liveness route remains public. The root `/metrics` route
also has a private-network IP allowlist in the production Nginx configuration.

## RAG uploads

RAG uploads use the authenticated multipart upload endpoint. The legacy
`/rag/upload/presign` route was removed because it issued arbitrary object PUT
URLs without authenticating or checking document ownership.
