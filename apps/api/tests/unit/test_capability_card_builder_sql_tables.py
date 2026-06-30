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

    operation = SimpleNamespace(
        scope="collection",
        collection_slug="ticket_network",
        operation="collection.sql.search_objects",
        operation_slug="instance.ticket_network.collection.sql.search_objects",
        name="Search SQL Objects",
        published=SimpleNamespace(
            title="Search SQL Objects",
            description="Search SQL catalog objects in the bound collection",
            result_kind="rows",
        ),
    )

    card = builder._build_collections_card([item], [operation])  # noqa: SLF001

    assert "таблицы:" in card
    assert "Перед работой с любой коллекцией сначала вызови `collection.info`" in card
    assert "правила работы:" not in card
    assert "рекомендуемый порядок" not in card
    assert "`collection.sql.search_objects`" not in card
    assert "`tenwork_tickets`" in card
    assert "`services`" in card


def test_collections_card_skips_collections_without_operations():
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

    assert card == ""


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

    assert "доступные операции:" not in card
    assert "рекомендуемый порядок" not in card
    assert "`collection.template.fill`" not in card
    assert "готовность" not in card.lower()
    assert "схема:" not in card.lower()


def test_system_operations_card_is_rendered_separately():
    builder = CapabilityCardBuilder()
    operation = SimpleNamespace(
        scope="system",
        operation="file.read",
        operation_slug="file.read",
        name="Read File",
        published=SimpleNamespace(
            canonical_name="file.read",
            title="Read File",
            description="Read a file by its canonical storage_uri",
            result_kind="generic",
        ),
    )

    card = builder._build_system_operations_card([operation])  # noqa: SLF001

    assert "## Системные операции" in card
    assert "`file.read`" in card
    assert "Read a file by its canonical storage_uri" in card
