from types import SimpleNamespace

from app.models.system_llm_role import SystemLLMRoleType
from app.services.system_llm_role_service import SystemLLMRoleService


class _RepoStub:
    def __init__(self, existing):
        self._existing = existing
        self.updated = []
        self.created = []

    async def get_active_role(self, role_type):
        return self._existing.get(role_type)

    async def create(self, role):
        self.created.append(role)
        self._existing[role.role_type] = role
        return role

    async def update(self, role):
        self.updated.append(role)
        return role


def _role(**kwargs):
    defaults = dict(
        role_type=SystemLLMRoleType.SYNTHESIZER,
        is_active=True,
        identity="custom identity",
        mission="custom mission",
        rules="custom rules",
        safety="custom safety",
        output_requirements="custom output",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


async def test_ensure_default_roles_does_not_override_existing_prompt_fields():
    service = SystemLLMRoleService(session=SimpleNamespace())
    existing = _role()
    repo = _RepoStub(existing={SystemLLMRoleType.SYNTHESIZER: existing})
    service.repo = repo

    await service.ensure_default_roles()

    assert existing.identity == "custom identity"
    assert existing.mission == "custom mission"
    assert existing.rules == "custom rules"
    assert existing.safety == "custom safety"
    assert existing.output_requirements == "custom output"


async def test_ensure_default_roles_backfills_only_empty_prompt_fields():
    service = SystemLLMRoleService(session=SimpleNamespace())
    existing = _role(identity="", mission=None)
    repo = _RepoStub(existing={SystemLLMRoleType.SYNTHESIZER: existing})
    service.repo = repo

    await service.ensure_default_roles()

    assert isinstance(existing.identity, str) and len(existing.identity) > 0
    assert isinstance(existing.mission, str) and len(existing.mission) > 0
    assert existing.rules == "custom rules"

