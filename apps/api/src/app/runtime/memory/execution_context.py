"""Application-provided execution context; selectors never enumerate projects."""
from typing import Any, Iterable


def memory_execution_context(scope_keys: Iterable[str], *, revision: int = 0) -> dict[str, Any]:
    keys = list(dict.fromkeys(scope_keys))
    teams = [key for key in keys if key.startswith("team.") and key != "team.all"]
    projects = [key for key in keys if key.startswith("project.") and key != "project.all"]
    return {"type": "execution_context", "revision": revision, "team_keys": teams,
            "project_keys": [*projects, "project.all"], "focused_project_keys": projects,
            "search_policy": {"teams": "always_use_all_context_teams",
                              "projects": "choose_known_projects_or_empty_for_non_project",
                              "project.all": "only_rules_common_to_all_projects"}}
