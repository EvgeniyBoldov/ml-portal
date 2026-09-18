from app.models.memory import FactScope, FactSource
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.project_context import PROJECT_SCOPE_SUBJECT, ProjectContext, _scope_keys


def test_project_scope_uses_structured_metadata_not_display_value() -> None:
    fact = FactDTO(
        scope=FactScope.USER, subject=PROJECT_SCOPE_SUBJECT, value="Portal, Billing",
        source=FactSource.MANUAL, metadata={"project_keys": ["portal", "billing", "unknown"]},
    )
    assert _scope_keys([fact], {"portal", "billing"}) == ["portal", "billing"]


def test_explicit_project_scope_overrides_default_without_picking_first() -> None:
    context = ProjectContext(explicit_project_keys=("billing",), default_project_keys=("portal", "billing"))
    assert context.effective_project_keys == ("billing",)
    assert context.source == "explicit"


def test_multi_project_default_stays_multi_project() -> None:
    context = ProjectContext(default_project_keys=("portal", "billing"))
    assert context.effective_project_keys == ("portal", "billing")
    assert context.as_dict()["ambiguous"] is False
