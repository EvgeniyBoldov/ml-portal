from __future__ import annotations

from urllib.parse import quote, urlparse

from app.services.credential_service import CredentialService
from app.services.mcp_jsonrpc_client import mcp_call_tool, mcp_initialize, mcp_result_error_message
from app.services.tool_instance.types import HealthCheckResult


class ToolInstanceHealthService:
    """Health-check orchestration for tool instances."""

    def __init__(self, host) -> None:
        self.host = host

    async def check_health(self, instance_id):
        instance = await self.host.get_instance(instance_id)

        if instance.is_local:
            instance.health_status = "healthy"
            await self.host.repo.update(instance)
            return HealthCheckResult(status="healthy", message="Local instance")

        try:
            result = await self.perform_health_check(instance)
            instance.health_status = result.status
            await self.host.repo.update(instance)
            return result
        except Exception as e:
            self.host.logger.error(f"Health check failed for instance {instance_id}: {e}")
            instance.health_status = "unhealthy"
            await self.host.repo.update(instance)
            return HealthCheckResult(status="unhealthy", message=str(e))

    async def perform_health_check(self, instance):
        connector_type = str(getattr(instance, "connector_type", "") or "").strip().lower()
        connector_subtype = str(getattr(instance, "connector_subtype", "") or "").strip().lower()

        if connector_type == "mcp":
            return await self._check_mcp_connector(instance)

        if connector_type == "data" and connector_subtype == "sql":
            return await self._check_sql_connector(instance)

        url = instance.url
        if not url:
            return HealthCheckResult(
                status="unknown",
                message="No URL configured",
            )

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, follow_redirects=True)
                if response.status_code < 500:
                    return HealthCheckResult(
                        status="healthy",
                        message=f"Connection successful (status: {response.status_code})",
                        details={"status_code": response.status_code},
                    )
                return HealthCheckResult(
                    status="unhealthy",
                    message=f"Server error (status: {response.status_code})",
                    details={"status_code": response.status_code},
                )
        except Exception as e:
            return HealthCheckResult(
                status="unhealthy",
                message=f"Connection failed: {str(e)}",
            )

    async def _check_mcp_connector(self, instance) -> HealthCheckResult:
        provider_url = str(instance.url or "").strip()
        if not provider_url:
            return HealthCheckResult(
                status="unhealthy",
                message="MCP connector has empty URL",
            )
        try:
            session_id = await mcp_initialize(provider_url=provider_url, timeout_s=10)
            return HealthCheckResult(
                status="healthy",
                message="MCP session initialized",
                details={"mcp_session_id_prefix": session_id[:8]},
            )
        except Exception as exc:
            return HealthCheckResult(
                status="unhealthy",
                message=f"MCP sync unavailable: {exc}",
            )

    async def _check_sql_connector(self, instance) -> HealthCheckResult:
        provider = getattr(instance, "access_via", None)
        if provider is None and getattr(instance, "access_via_instance_id", None):
            provider = await self.host.repo.get_by_id(instance.access_via_instance_id)

        if not provider:
            return HealthCheckResult(
                status="unhealthy",
                message="No MCP provider linked (access_via_instance_id is not set)",
            )
        if str(getattr(provider, "connector_type", "") or "").strip().lower() != "mcp":
            return HealthCheckResult(
                status="unhealthy",
                message="Linked provider is not MCP connector",
            )
        provider_url = str(getattr(provider, "url", "") or "").strip()
        if not provider_url:
            return HealthCheckResult(
                status="unhealthy",
                message="Linked MCP provider has empty URL",
            )

        try:
            session_id = await mcp_initialize(provider_url=provider_url, timeout_s=10)
        except Exception as exc:
            return HealthCheckResult(
                status="unhealthy",
                message=f"MCP sync unavailable: {exc}",
            )

        config = instance.config or {}
        expected_db = str(config.get("database_name") or "").strip()

        cred_service = CredentialService(self.host.session)
        creds = await cred_service.resolve_credentials(instance_id=instance.id, strategy="ANY")
        payload = (creds.payload or {}) if creds else {}
        username = payload.get("username")
        password = payload.get("password")

        dsn: str | None = None
        try:
            dsn = self._build_postgres_dsn(
                instance_url=instance.url,
                database_name=expected_db or None,
                username=username,
                password=password,
            )
        except ValueError:
            dsn = None

        arguments = {"sql": "SELECT current_database() AS current_database"}
        if dsn:
            arguments["db_dsn"] = dsn

        try:
            result = await mcp_call_tool(
                provider_url=provider_url,
                session_id=session_id,
                tool_name="execute_sql",
                arguments=arguments,
                timeout_s=15,
            )
        except Exception as exc:
            return HealthCheckResult(
                status="unknown",
                message=f"MCP sync available, but DB check failed: {exc}",
            )

        tool_error = mcp_result_error_message(result)
        if tool_error:
            return HealthCheckResult(
                status="unknown",
                message=f"MCP sync available, but DB check failed: {tool_error}",
            )

        rows = (result.get("structuredContent") or {}).get("rows") or []
        current_db = ""
        if rows and isinstance(rows[0], dict):
            current_db = str(rows[0].get("current_database") or "").strip()

        if expected_db and current_db and expected_db == current_db:
            return HealthCheckResult(
                status="healthy",
                message=f"DB reachable via MCP, database verified: {current_db}",
                details={"database_name": current_db, "provider_slug": provider.slug},
            )

        if expected_db and current_db and expected_db != current_db:
            return HealthCheckResult(
                status="unknown",
                message=f"MCP sync available, DB responded but name mismatch: expected '{expected_db}', got '{current_db}'",
                details={"expected_database": expected_db, "actual_database": current_db},
            )

        if expected_db and not current_db:
            return HealthCheckResult(
                status="unknown",
                message="MCP sync available, but DB name verification returned empty result",
                details={"expected_database": expected_db},
            )

        return HealthCheckResult(
            status="unknown",
            message="MCP sync available, but database_name is not configured for strict verification",
            details={"provider_slug": provider.slug},
        )

    @staticmethod
    def _build_postgres_dsn(
        *,
        instance_url: str,
        database_name: str | None,
        username: str | None,
        password: str | None,
    ) -> str:
        raw_url = str(instance_url or "").strip()
        parsed = urlparse(raw_url)
        if not parsed.hostname:
            parsed = urlparse(f"//{raw_url}")
        if not parsed.hostname:
            raise ValueError("SQL connector URL must include hostname")

        db_name = (database_name or "").strip() or (parsed.path or "").strip("/ ")
        if not db_name:
            raise ValueError("database_name is required")

        user = (username or "").strip() or (parsed.username or "").strip()
        pwd = (password or "").strip() or (parsed.password or "").strip()
        if not user or not pwd:
            raise ValueError("username/password are required")

        port = parsed.port or 5432
        credentials = f"{quote(user)}:{quote(pwd)}"
        return f"postgresql://{credentials}@{parsed.hostname}:{port}/{db_name}"
