from app.runtime.memory.search import _kinds_for_direction


def test_direction_narrows_memory_kinds_when_caller_did_not_supply_kinds() -> None:
    assert _kinds_for_direction("project rules and policy") == {"rule", "constraint"}
    assert _kinds_for_direction("описание процедуры") == {"procedure"}
    assert _kinds_for_direction("term definition") == {"term", "description"}
    assert _kinds_for_direction("general context") == set()
