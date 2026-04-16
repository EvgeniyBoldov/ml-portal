from __future__ import annotations

from app.models.tool_instance import InstanceKind, InstancePlacement, ToolInstance


class ToolInstanceLocalManager:
    """Ensures canonical local service instances for collection runtime."""

    def __init__(self, host) -> None:
        self.host = host

    async def ensure_local_service_instance(
        self,
        *,
        slug: str,
        name: str,
        description: str,
        domain: str,
        provider_kind: str,
    ) -> tuple[ToolInstance, bool, bool]:
        existing = await self.host.repo.get_by_slug(slug)
        if existing is None:
            created_instance = await self.host.create_instance(
                slug=slug,
                name=name,
                description=description,
                instance_kind=InstanceKind.SERVICE.value,
                connector_type="mcp",
                placement=InstancePlacement.LOCAL.value,
                domain=domain,
                url="",
                config={"provider_kind": provider_kind},
                allow_local=True,
            )
            created_instance.health_status = "healthy"
            created_instance.is_active = True
            created_instance = await self.host.repo.update(created_instance)
            self.host.logger.info("Created local service instance: %s", slug)
            return created_instance, True, False

        updated = False
        if existing.instance_kind != InstanceKind.SERVICE.value:
            existing.instance_kind = InstanceKind.SERVICE.value
            updated = True
        if getattr(existing, "connector_type", None) != "mcp":
            existing.connector_type = "mcp"
            updated = True
        if getattr(existing, "connector_subtype", None) is not None:
            existing.connector_subtype = None
            updated = True
        if existing.placement != InstancePlacement.LOCAL.value:
            existing.placement = InstancePlacement.LOCAL.value
            existing.url = ""
            updated = True
        if existing.domain != domain:
            existing.domain = domain
            updated = True
        expected_config = {"provider_kind": provider_kind}
        if existing.config != expected_config:
            existing.config = expected_config
            updated = True
        if not existing.is_active:
            existing.is_active = True
            updated = True
        if existing.health_status != "healthy":
            existing.health_status = "healthy"
            updated = True

        if updated:
            existing = await self.host.repo.update(existing)
            self.host.logger.info("Updated local service instance: %s", slug)
        return existing, False, updated
