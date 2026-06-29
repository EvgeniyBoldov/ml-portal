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
        usage_rules="Сначала inspect, потом search",
        description="fallback",
        remote_tables=["tenwork_tickets", "services"],
    )

    card = builder._build_collections_card([item], [])  # noqa: SLF001

    assert "таблицы:" in card
    assert "правила работы: Сначала inspect, потом search" in card
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

    card = builder._build_collections_card([item], [])  # noqa: SLF001

    assert "готовность: schema_stale" in card
    assert "схема: stale" in card
    assert "отсутствует: schema_stale" in card


def test_collections_card_groups_collection_operations_with_descriptions():
    builder = CapabilityCardBuilder()
    item = SimpleNamespace(
        collection_slug="template",
        slug="template_data",
        collection_type="template",
        domain="collection.template",
        entity_type=None,
        usage_purpose="Заполнять заявки по шаблону",
        data_description="Шаблоны заявок",
        description="fallback",
        remote_tables=[],
        readiness=SimpleNamespace(
            status="ready",
            schema_freshness="fresh",
            missing_requirements=[],
        ),
    )
    operation = SimpleNamespace(
        scope="collection",
        collection_slug="template",
        operation="collection.template.fill",
        operation_slug="instance.template.collection.template.fill",
        name="Fill Template",
        published=SimpleNamespace(
            title="Fill Template",
            description="Fill a template with values and return a generated file",
            result_kind="file",
        ),
    )

    card = builder._build_collections_card([item], [operation])  # noqa: SLF001

    assert "доступные действия:" in card
    assert "`instance.template.collection.template.fill`" in card
    assert "каноническое имя: collection.template.fill" in card
    assert "Fill a template with values and return a generated file" in card
    assert "результат: file" in card
