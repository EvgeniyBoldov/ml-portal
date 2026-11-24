from types import SimpleNamespace

from app.models.system_llm_role import SystemLLMRoleType
from app.services.system_llm_role_service import SystemLLMRoleService


class _RepoStub:
    def __init__(self, existing):
        self._existing = existing
        self.updated = []
        self.created = []

    async def get_active_role(self, role_type, *, for_update=False):
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


async def test_ensure_default_roles_installs_all_three_orchestration_prompts():
    service = SystemLLMRoleService(session=SimpleNamespace())
    repo = _RepoStub(existing={})
    service.repo = repo

    roles = await service.ensure_default_roles()

    from app.services.orchestration_prompts import PLANNER_PROMPT_V3, SYNTHESIZER_PROMPT_V3
    from app.services.turn_preflight_prompt_v3 import TURN_PREFLIGHT_PROMPT_V3

    for role_type, prompt in (
        (SystemLLMRoleType.TURN_PREFLIGHT, TURN_PREFLIGHT_PROMPT_V3),
        (SystemLLMRoleType.PLANNER, PLANNER_PROMPT_V3),
        (SystemLLMRoleType.SYNTHESIZER, SYNTHESIZER_PROMPT_V3),
    ):
        role = roles[role_type]
        assert role in repo.created
        for field, value in prompt.items():
            assert getattr(role, field) == value


async def test_fill_prompt_defaults_only_updates_empty_sections_of_the_selected_role():
    from app.services.system_role_defaults.synthesizer import SYNTHESIZER_PROMPT_V3

    service = SystemLLMRoleService(session=SimpleNamespace())
    selected = _role(
        identity="", mission=None, rules=" \t", examples=[], model=None, temperature=None,
        extras={"keep": True},
    )
    other = _role(role_type=SystemLLMRoleType.PLANNER, identity="")
    repo = _RepoStub({
        SystemLLMRoleType.SYNTHESIZER: selected,
        SystemLLMRoleType.PLANNER: other,
    })
    service.repo = repo

    assert await service.fill_active_prompt_defaults(SystemLLMRoleType.SYNTHESIZER) is selected
    for field in ("identity", "mission", "rules"):
        assert getattr(selected, field) == SYNTHESIZER_PROMPT_V3[field]
    assert selected.safety == "custom safety"
    assert selected.output_requirements == "custom output"
    assert selected.examples == []
    assert selected.extras == {"keep": True}
    assert selected.model is None
    assert selected.temperature is None
    assert other.identity == ""
    assert repo.created == []

    await service.fill_active_prompt_defaults(SystemLLMRoleType.SYNTHESIZER)
    assert repo.updated == [selected]
