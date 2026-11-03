"""Broker-bound, per-call clients for the embedded Atlassian tool server.

The native HTTP middleware assumes URLs/credentials come from server env. Portal
instead authenticates the call at the broker and binds its registered source.
No env mutation, URL allowlist mutation, or global fetcher patching is needed.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import logging
import os
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from requests.adapters import HTTPAdapter
from requests.exceptions import InvalidURL

from helpers.adapter_auth import _value, resolve_request_credential, upstream_auth_headers
from helpers.mcp_adapter import MCPAdapter
from helpers.observability import safe_target
from helpers.secret_broker import ResolvedCredential

logger = logging.getLogger("mcp.atlassian_auth")


def source_url(value: str, *, product: str = "jira") -> str:
    """Normalize the registered service root while retaining a context path."""
    parsed = urlsplit(value.strip())
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or "\\" in value or any(ord(c) < 32 for c in value)):
        raise ValueError("Broker source URL must be an HTTP service URL without credentials or query")
    parsed.port  # Validate malformed ports before any HTTP request.
    path = parsed.path.rstrip("/")
    suffixes = ("/rest/api/3", "/rest/api/2", "/rest/api") if product == "jira" else ("/rest/api", "/api/v2")
    for suffix in suffixes:
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    return urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))


def _origin(url: str) -> tuple[str, str | None, int]:
    parsed = urlsplit(url)
    return parsed.scheme.lower(), parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


class SourceBoundAdapter(HTTPAdapter):
    """Credentials may leave this client only for the broker-confirmed source."""

    def __init__(self, url: str) -> None:
        self.source_url = url
        super().__init__(max_retries=0)

    def send(self, request: Any, **kwargs: Any) -> Any:
        parsed = urlsplit(request.url)
        path = unquote(parsed.path)
        root = unquote(urlsplit(self.source_url).path).rstrip("/")
        if (parsed.username or parsed.password or _origin(request.url) != _origin(self.source_url)
                or "\\" in path or unquote(path) != path
                or any(part == ".." for part in path.split("/"))
                or (root and path != root and not path.startswith(root + "/"))):
            raise InvalidURL("Request is outside the broker-confirmed data source")
        host_header = request.headers.get("Host")
        if host_header and host_header.lower() != parsed.netloc.lower():
            raise InvalidURL("Host header is outside the broker-confirmed data source")
        kwargs["proxies"] = {}
        return super().send(request, **kwargs)


def _reject_redirect(response: Any, **kwargs: Any) -> Any:
    if response.is_redirect:
        response.close()
        raise InvalidURL("Redirects from broker-bound Atlassian sources are not permitted")
    return response


@dataclass
class SourceClient:
    product: str
    url: str
    fetcher: Any
    session: Any


_current_client: ContextVar[SourceClient | None] = ContextVar("atlassian_source_client", default=None)


def build_source_client(credential: ResolvedCredential, tool: str) -> SourceClient:
    # Imports stay here so the generic adapter never depends on Atlassian SDKs.
    from mcp_atlassian.jira import JiraConfig, JiraFetcher
    from mcp_atlassian.confluence import ConfluenceConfig, ConfluenceFetcher

    product = "confluence" if tool.startswith("confluence_") else "jira"
    url = source_url(credential.source_url, product=product)
    auth_type = credential.auth_type.strip().lower()
    config_args: dict[str, Any] = {
        "url": url,
        "ssl_verify": os.environ.get("VERIFY_SSL", "true").lower() == "true",
    }
    if auth_type == "token":
        config_args.update(auth_type="pat", personal_token=_value(
            credential.payload, f"{product}_personal_token", "token", "pat",
            "personal_token", "personal_access_token", "api_token",
        ))
    elif auth_type == "basic":
        config_args.update(
            auth_type="basic", username=_value(credential.payload, "username", "email"),
            api_token=_value(credential.payload, "password", "api_token", strip=False),
        )
    elif auth_type in {"oauth", "bearer", "api_key"}:
        # Use the broker-declared scheme directly; no global OAuth client or
        # fallback PAT is involved in authenticating this source.
        config_args.update(auth_type="external")
    else:
        raise ValueError("Unsupported broker credential auth_type for Atlassian")
    config_type, fetcher_type = (ConfluenceConfig, ConfluenceFetcher) if product == "confluence" else (JiraConfig, JiraFetcher)
    fetcher = fetcher_type(config=config_type(**config_args))
    sdk = fetcher.confluence if product == "confluence" else fetcher.jira
    session = sdk._session
    if config_args["auth_type"] == "external":
        session.headers.update(upstream_auth_headers(credential))
    # Replace env-based SSRF trust with a transport bound to this verified source.
    # The client is private to one tools/call and cannot follow another URL.
    for adapter in set(session.adapters.values()):
        adapter.close()
    session.adapters.clear()
    session.mount("http://", SourceBoundAdapter(url))
    session.mount("https://", SourceBoundAdapter(url))
    session.trust_env = False
    session.hooks["response"] = [_reject_redirect]
    return SourceClient(product, url, fetcher, session)


class PortalAtlassianAdapter(MCPAdapter):
    async def _resolve_credential(
        self, arguments: dict[str, Any], request_id: str, tool: str,
    ) -> ResolvedCredential:
        # Reuse the API's existing control-plane settings. A caller cannot
        # nominate its own broker and manufacture a trusted private source URL.
        broker_url = os.environ.get("MCP_CREDENTIAL_BROKER_BASE_URL", "http://api:8000").rstrip("/")
        broker_path = os.environ.get("MCP_CREDENTIAL_BROKER_RESOLVE_PATH", "/api/v1/internal/mcp/credentials/resolve")
        return await resolve_request_credential(
            arguments, timeout_s=self.config.broker_timeout_s, allow_raw=False,
            request_id=request_id, server=self.config.name, tool=tool,
            trusted_broker_url=broker_url + broker_path,
        )

    def _source_url(self, arguments: dict[str, Any], credential: ResolvedCredential, tool: str) -> str:
        context = arguments.get("instance_context")
        context = context if isinstance(context, dict) else {}
        if not credential.source_url:
            raise ValueError("Broker did not return the registered data source URL; update the API")
        if context.get("data_instance_id") and str(context["data_instance_id"]) != credential.instance_id:
            raise ValueError("Broker credential does not match the operation data source")
        return source_url(credential.source_url, product="confluence" if tool.startswith("confluence_") else "jira")

    @asynccontextmanager
    async def _upstream_context(self, credential: ResolvedCredential | None, tool: str) -> AsyncIterator[None]:
        client = None
        if credential:
            preparation = asyncio.create_task(asyncio.to_thread(build_source_client, credential, tool))
            try:
                client = await asyncio.shield(preparation)
            except asyncio.CancelledError:
                # Shield preparation so a late-created session is still closed.
                def close_prepared(task: asyncio.Task[SourceClient]) -> None:
                    if not task.cancelled() and task.exception() is None:
                        task.result().session.close()
                preparation.add_done_callback(close_prepared)
                raise
        token = _current_client.set(client)
        try:
            if client:
                logger.info(
                    "atlassian_source_client_bound credential_id=%s data_instance_id=%s "
                    "auth_type=%s product=%s target=%s",
                    credential.credential_id, credential.instance_id, credential.auth_type,
                    client.product, safe_target(client.url),
                )
            yield
        finally:
            _current_client.reset(token)
            if client:
                client.session.close()


class SourceClientMiddleware:
    """Supply native tool dependencies from the current broker-bound call."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = scope.setdefault("state", {})
        client = _current_client.get()
        if client:
            config = client.fetcher.config
            state[f"{client.product}_fetcher"] = client.fetcher
            state["portal_source_bound"] = True
            state["portal_source_auth_type"] = config.auth_type
            state["portal_username_present"] = bool(config.username)
            state["portal_api_token_present"] = bool(config.api_token)
            state["portal_token_present"] = bool(config.personal_token)
        await self.app({**scope, "state": state}, receive, send)


def build_upstream_app() -> Any:
    from fastmcp import FastMCP
    from starlette.middleware import Middleware
    from mcp_atlassian.servers.main import AtlassianMCP
    from mcp_atlassian.servers.context import MainAppContext
    from mcp_atlassian.servers.jira import jira_mcp
    from mcp_atlassian.servers.confluence import confluence_mcp
    from mcp_atlassian.utils.io import is_read_only_mode
    from mcp_atlassian.utils.tools import get_enabled_tools
    from mcp_atlassian.utils.toolsets import get_enabled_toolsets

    @asynccontextmanager
    async def lifespan(app: Any) -> AsyncIterator[dict[str, Any]]:
        # Preserve native tool/read-only filters, with no global service clients.
        yield {"app_lifespan_context": MainAppContext(
            read_only=is_read_only_mode(), enabled_tools=get_enabled_tools(),
            enabled_toolsets=get_enabled_toolsets(),
        )}

    class PortalAtlassianMCP(AtlassianMCP):
        def _tool_filter_context(self) -> dict[str, Any] | None:
            context = super()._tool_filter_context()
            if context is not None:
                # Availability is supplied by the broker at call time. Schema
                # discovery needs no endpoint, placeholder PAT or credential.
                context["header_based_services"] = {"jira": True, "confluence": True}
            return context

    server = PortalAtlassianMCP(name="Portal Atlassian tools", lifespan=lifespan)
    server.mount(jira_mcp, namespace="jira")
    server.mount(confluence_mcp, namespace="confluence")
    # Invoke the base factory intentionally: Portal replaces the native HTTP
    # header/env authentication middleware with its broker-authenticated context.
    return FastMCP.http_app(
        server, path="/mcp", stateless_http=True, transport="streamable-http",
        middleware=[Middleware(SourceClientMiddleware)],
    )
