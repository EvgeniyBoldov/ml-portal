"""Review permits individual approve/reject decisions only."""
from app.api.v1.routers.admin import semantic_memory


def test_bulk_term_approval_is_not_exposed() -> None:
    assert not hasattr(semantic_memory, "bulk_approve_shadow_terms")
    assert not any("bulk-approve" in route.path for route in semantic_memory.router.routes)
