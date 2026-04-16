import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.agents.tool_router import ToolRouter, ToolRouterError
from app.models.tool_release import ToolReleaseStatus
from app.services.tool_release_service import ReleasePinnedError, ToolReleaseService


def _release_row(
    *,
    release_id,
    version: int,
    status: str,
    ops: list[str],
    risk: str = "low",
    idempotent: bool = True,
    timeout_s: int | None = None,
):
    release = SimpleNamespace(
        id=release_id,
        version=version,
        status=status,
        routing_ops=ops,
        routing_risk_level=risk,
        routing_idempotent=idempotent,
        exec_timeout_s=timeout_s,
    )
    return (release, "tool-slug")


@pytest.mark.asyncio
async def test_tool_router_uses_pinned_release_when_available():
    session = AsyncMock()
    pinned_id = uuid4()
    result = AsyncMock()
    result.all.return_value = [
        _release_row(
            release_id=pinned_id,
            version=3,
            status=ToolReleaseStatus.ACTIVE.value,
            ops=["execute"],
            timeout_s=42,
        )
    ]
    session.execute.return_value = result

    router = ToolRouter(session)
    selection = await router.select(
        "tool-slug",
        "execute",
        pinned_release_id=pinned_id,
    )

    assert selection.tool_release_id == pinned_id
    assert selection.exec_timeout_s == 42


@pytest.mark.asyncio
async def test_tool_router_fails_closed_when_pinned_release_unavailable():
    session = AsyncMock()
    pinned_id = uuid4()
    other_id = uuid4()

    result = AsyncMock()
    result.all.return_value = [
        _release_row(
            release_id=other_id,
            version=5,
            status=ToolReleaseStatus.ACTIVE.value,
            ops=["execute"],
        )
    ]
    session.execute.return_value = result

    router = ToolRouter(session)

    with pytest.raises(ToolRouterError) as exc:
        await router.select(
            "tool-slug",
            "execute",
            pinned_release_id=pinned_id,
        )

    assert "Pinned release" in str(exc.value)


@pytest.mark.asyncio
async def test_archive_release_forbidden_when_pinned_in_binding():
    session = AsyncMock()
    pinned_binding_result = AsyncMock()
    pinned_binding_result.scalar_one_or_none.return_value = uuid4()
    session.execute.return_value = pinned_binding_result

    service = ToolReleaseService(session)
    service.tool_repo = AsyncMock()
    service.release_repo = AsyncMock()

    release = SimpleNamespace(
        id=uuid4(),
        tool_id=uuid4(),
        version=7,
        status=ToolReleaseStatus.ACTIVE.value,
    )

    with pytest.raises(ReleasePinnedError):
        await service._archive_release(release)

    service.release_repo.update.assert_not_called()
    session.commit.assert_not_called()
