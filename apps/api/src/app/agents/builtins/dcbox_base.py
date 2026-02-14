"""
DCBox (NetBox fork) — базовый класс для HTTP-based remote tools.

Все DCBox tools наследуют RemoteApiTool, который:
1. Резолвит credentials через CredentialService
2. Делает HTTP запросы к remote instance (NetBox API)
3. Обрабатывает пагинацию и ошибки
"""
from __future__ import annotations
from typing import Any, Dict, Optional, List
from uuid import UUID

import httpx

from app.core.logging import get_logger
from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool

logger = get_logger(__name__)

DEFAULT_LIMIT = 10
MAX_LIMIT = 200
REQUEST_TIMEOUT = 30


class RemoteApiTool(VersionedTool):
    """
    Базовый класс для tools, работающих с remote HTTP API.

    Подклассы должны определить:
    - tool_slug, tool_group, name, description (как обычный VersionedTool)
    - requires_instance = True
    """
    requires_instance = True

    async def _resolve_instance_info(
        self, ctx: ToolContext
    ) -> Optional[Dict[str, Any]]:
        """
        Получить URL и credentials для remote instance из контекста.

        Router кладёт tool_instances_map в exec_request,
        а ChatStreamService прокидывает его в ctx.extra.
        """
        instances_map = ctx.extra.get("tool_instances_map", {})
        logger.debug(
            f"Resolving instance for {self.tool_slug}, "
            f"available_keys={list(instances_map.keys())}"
        )
        info = instances_map.get(self.tool_slug)
        if not info:
            # Fallback: поискать по tool_group
            for slug, data in instances_map.items():
                if slug.startswith(f"{self.tool_group}."):
                    info = data
                    break
        return info

    async def _get_credentials(
        self, ctx: ToolContext, instance_id: str
    ) -> Optional[Dict[str, Any]]:
        """Resolve and decrypt credentials for the instance."""
        from app.core.db import get_session_factory
        from app.services.credential_service import CredentialService

        session_factory = get_session_factory()
        async with session_factory() as session:
            service = CredentialService(session)
            decrypted = await service.resolve_credentials(
                instance_id=UUID(instance_id),
                strategy="ANY",
                user_id=UUID(ctx.user_id) if ctx.user_id else None,
                tenant_id=UUID(ctx.tenant_id) if ctx.tenant_id else None,
            )
            if decrypted:
                return {
                    "auth_type": decrypted.auth_type,
                    "payload": decrypted.payload,
                }
        return None

    async def _get_instance_url(self, instance_id: str) -> Optional[str]:
        """Get instance URL from DB."""
        from app.core.db import get_session_factory
        from app.services.tool_instance_service import ToolInstanceService

        session_factory = get_session_factory()
        async with session_factory() as session:
            service = ToolInstanceService(session)
            instance = await service.get_instance(UUID(instance_id))
            return instance.url if instance else None

    def _build_headers(self, credentials: Dict[str, Any]) -> Dict[str, str]:
        """Build HTTP headers from credentials."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        auth_type = credentials.get("auth_type", "token")
        payload = credentials.get("payload", {})

        if auth_type == "token":
            token = payload.get("token", "")
            headers["Authorization"] = f"Token {token}"
        elif auth_type == "api_key":
            key = payload.get("api_key", "")
            headers["Authorization"] = f"Token {key}"
        elif auth_type == "basic":
            import base64
            username = payload.get("username", "")
            password = payload.get("password", "")
            encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

        return headers

    async def _api_get(
        self,
        base_url: str,
        path: str,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make GET request to remote API."""
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, verify=False
        ) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code >= 400:
                raise Exception(
                    f"API error {resp.status_code}: {resp.text[:500]}"
                )
            return resp.json()

    async def _fetch_list(
        self,
        ctx: ToolContext,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> ToolResult:
        """
        Generic list fetcher for NetBox API endpoints.

        Handles: instance resolution, credentials, pagination, errors.
        """
        log = ctx.tool_logger(self.tool_slug)
        log.info("Starting list fetch", endpoint=endpoint, limit=limit, offset=offset)

        instance_info = await self._resolve_instance_info(ctx)
        if not instance_info:
            log.error("No instance configured")
            return ToolResult.fail(
                f"No instance configured for tool '{self.tool_slug}'. "
                "Please create a remote instance and bind it to the agent.",
                logs=log.entries_dict(),
            )

        instance_id = instance_info.get("instance_id")
        if not instance_id:
            log.error("Instance ID not found in context")
            return ToolResult.fail("Instance ID not found in context",
                                   logs=log.entries_dict())

        log.debug("Resolving credentials", instance_id=instance_id)
        credentials = await self._get_credentials(ctx, instance_id)
        if not credentials:
            log.error("No credentials found", instance_id=instance_id)
            return ToolResult.fail(
                f"No credentials found for instance '{instance_id}'. "
                "Please create credentials for this instance.",
                logs=log.entries_dict(),
            )

        base_url = await self._get_instance_url(instance_id)
        if not base_url:
            log.error("Instance URL not found", instance_id=instance_id)
            return ToolResult.fail(f"Instance '{instance_id}' URL not found",
                                   logs=log.entries_dict())

        headers = self._build_headers(credentials)

        effective_limit = min(limit, MAX_LIMIT)
        query_params = {
            "limit": effective_limit,
            "offset": offset,
            **(params or {}),
        }
        # Remove None values
        query_params = {k: v for k, v in query_params.items() if v is not None}

        log.info("Calling remote API", url=base_url, params_count=len(query_params))

        try:
            data = await self._api_get(base_url, endpoint, headers, query_params)

            results = data.get("results", [])
            count = data.get("count", len(results))

            log.info("API call succeeded", results_count=len(results),
                     total_count=count, has_more=count > (offset + len(results)))

            return ToolResult.ok(
                data={
                    "results": results,
                    "count": count,
                    "returned": len(results),
                    "has_more": count > (offset + len(results)),
                },
                logs=log.entries_dict(),
            )
        except Exception as e:
            logger.error(f"DCBox API call failed: {e}", exc_info=True)
            log.error("API request failed", error=str(e), endpoint=endpoint)
            return ToolResult.fail(f"API request failed: {str(e)}",
                                   logs=log.entries_dict())

    async def _fetch_detail(
        self,
        ctx: ToolContext,
        endpoint: str,
        item_id: int,
    ) -> ToolResult:
        """Fetch a single item by ID."""
        log = ctx.tool_logger(self.tool_slug)
        log.info("Starting detail fetch", endpoint=endpoint, item_id=item_id)

        instance_info = await self._resolve_instance_info(ctx)
        if not instance_info:
            log.error("No instance configured")
            return ToolResult.fail(f"No instance configured for '{self.tool_slug}'",
                                   logs=log.entries_dict())

        instance_id = instance_info.get("instance_id")
        credentials = await self._get_credentials(ctx, instance_id)
        if not credentials:
            log.error("No credentials found", instance_id=instance_id)
            return ToolResult.fail(f"No credentials for instance '{instance_id}'",
                                   logs=log.entries_dict())

        base_url = await self._get_instance_url(instance_id)
        if not base_url:
            log.error("Instance URL not found")
            return ToolResult.fail(f"Instance URL not found",
                                   logs=log.entries_dict())

        headers = self._build_headers(credentials)

        try:
            log.debug("Calling remote API", url=base_url, path=f"{endpoint}{item_id}/")
            data = await self._api_get(
                base_url, f"{endpoint}{item_id}/", headers
            )
            log.info("Detail fetch succeeded", item_id=item_id)
            return ToolResult.ok(data={"item": data}, logs=log.entries_dict())
        except Exception as e:
            logger.error(f"DCBox API detail failed: {e}", exc_info=True)
            log.error("API request failed", error=str(e), item_id=item_id)
            return ToolResult.fail(f"API request failed: {str(e)}",
                                   logs=log.entries_dict())
