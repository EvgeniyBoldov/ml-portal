from types import SimpleNamespace

from app.agents.runtime.capability_card_builder import CapabilityCardBuilder


def test_collections_card_includes_remote_tables_preview():
    builder = CapabilityCardBuilder()
    item = SimpleNamespace(
        collection_slug="ticket_network",
        slug="sql_test",
        collection_type="sql",
        domain="collection.sql",
        entity_type=None,
        usage_purpose="purpose",
        data_description="description",
        description="fallback",
        remote_tables=["tenwork_tickets", "services"],
    )

    card = builder._build_collections_card([item])  # noqa: SLF001

    assert "tables:" in card
    assert "`tenwork_tickets`" in card
    assert "`services`" in card


def test_collections_card_includes_readiness_status_and_missing_requirements():
    builder = CapabilityCardBuilder()
    item = SimpleNamespace(
        collection_slug="ticket_network",
        slug="sql_test",
        collection_type="sql",
        domain="collection.sql",
        entity_type=None,
        usage_purpose="purpose",
        data_description="description",
        description="fallback",
        remote_tables=["tenwork_tickets"],
        readiness=SimpleNamespace(
            status="schema_stale",
            schema_freshness="stale",
            missing_requirements=["schema_stale"],
        ),
    )

    card = builder._build_collections_card([item])  # noqa: SLF001

    assert "readiness: schema_stale" in card
    assert "schema: stale" in card
    assert "missing: schema_stale" in card
