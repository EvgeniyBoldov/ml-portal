from types import SimpleNamespace

from app.agents.runtime.agent_prompt_renderer import AgentPromptRenderer


def test_render_base_prompt_preserves_compiled_prompt():
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

    assert rendered == exec_request.prompt
