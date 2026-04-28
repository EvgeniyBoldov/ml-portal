from types import SimpleNamespace

from app.agents.runtime.agent_prompt_renderer import AgentPromptRenderer


def test_sql_prompt_override_replaces_hardcoded_coll_name_and_adds_guidance():
    renderer = AgentPromptRenderer()
    exec_request = SimpleNamespace(
        prompt=(
            "# Tool Use Rules\n"
            "Для SQL запросов обязательно используй таблицу coll_a0eebc99_ticket_network.\n"
        ),
        resolved_data_instances=[
            SimpleNamespace(
                collection_type="sql",
                domain="collection.sql",
                collection_slug="ticket_network",
                slug="sql_test",
                remote_tables=["tenwork_tickets", "services"],
            )
        ],
    )

    rendered = renderer.render_base_prompt(exec_request=exec_request)

    assert "coll_a0eebc99_ticket_network" not in rendered
    assert "обязательно используй таблицу" not in rendered.lower()
    assert "## SQL Runtime Override" in rendered
    assert "`tenwork_tickets`" in rendered
    assert "`services`" in rendered
