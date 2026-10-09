"""Explicit source adapters and the runtime dataset protocol."""
from __future__ import annotations

from typing import Any
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class ResultMeta(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str | None = None
    total: int | None = Field(default=None, ge=0, validation_alias=AliasChoices("total", "count"))
    has_next: bool | None = None
    next_arguments: dict[str, Any] | None = None
    complete: bool | None = None


class ResultPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: list[Any]
    meta: ResultMeta = Field(default_factory=ResultMeta)

    @model_validator(mode="after")
    def validate_coverage(self) -> "ResultPage":
        if self.meta.complete is True and (self.meta.has_next is True or
                (self.meta.total is not None and len(self.value) < self.meta.total)):
            raise ValueError("complete source coverage conflicts with pagination or total")
        return self


def normalize_result(payload: Any, source_tool: str, arguments: dict[str, Any]) -> ResultPage:
    """Never infer collection paths from arbitrary JSON. Known adapters own them."""
    if isinstance(payload, dict) and set(payload) == {"value", "meta"}:
        return ResultPage.model_validate(payload)
    if source_tool == "netbox_search_objects":
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("NetBox search response must contain per-type results")
        pages = []
        types = []
        for group in payload["results"]:
            if not isinstance(group, dict) or not isinstance(group.get("object_type"), str):
                raise ValueError("NetBox search group must declare its object_type")
            types.append(group["object_type"])
            pages.append(normalize_result(group, "netbox_get_objects", arguments))
        expected = arguments.get("object_types") or payload.get("searched_types") or types
        errors = payload.get("errors", [])
        if not isinstance(errors, list) or len(set(types)) != len(types):
            raise ValueError("Invalid NetBox search type/error metadata")
        successful = not errors and set(types) == set(expected)
        totals = [page.meta.total for page in pages]
        total = sum(totals) if successful and all(value is not None for value in totals) else None
        continuations = [page.meta.next_arguments for page in pages if page.meta.has_next]
        offsets = {item["offset"] for item in continuations}
        if len(offsets) > 1:
            raise ValueError("NetBox search continuations disagree on the next offset")
        more = True if continuations else (False if all(page.meta.has_next is False for page in pages) else None)
        complete = all(page.meta.complete is True for page in pages) if successful else False
        if successful and any(page.meta.complete is None for page in pages):
            complete = None
        return ResultPage(value=[item for page in pages for item in page.value],
            meta=ResultMeta(source="netbox", total=total, has_next=more,
                complete=complete, next_arguments={**arguments, "offset": next(iter(offsets))} if offsets else None,
                searched_types=list(expected), successful_types=types, errors=errors,
                coverage_incomplete=not successful))
    if source_tool in {"netbox_get_objects", "netbox_get_device", "netbox_search_devices", "netbox_list_sites"}:
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("NetBox collection response must contain a results array")
        items = payload["results"]
        total = ResultMeta.model_validate({"total": payload.get("count")}).total
        more = bool(payload["next"]) if "next" in payload else None
        next_args = None
        if more:
            from urllib.parse import parse_qs, urlparse
            params = parse_qs(urlparse(str(payload["next"])).query)
            if "offset" not in params:
                raise ValueError("NetBox continuation is missing offset")
            next_args = {**arguments, "offset": int(params["offset"][0])}
            if next_args["offset"] <= int(arguments.get("offset", 0)):
                raise ValueError("NetBox continuation must advance the offset")
            if "limit" in params:
                next_args["limit"] = int(params["limit"][0])
        # Exact lookup intentionally returns only its matching page.
        start = int(arguments.get("offset", 0))
        if more is None and total is None:
            complete = None
        else:
            complete = not more and start == 0 and (total is None or len(items) >= total)
        return ResultPage(value=items, meta=ResultMeta(source="netbox", total=total,
            has_next=more, next_arguments=next_args, complete=complete))
    if source_tool == "jira_search_issues":
        if not isinstance(payload, dict) or not isinstance(payload.get("issues"), list):
            raise ValueError("Jira search response must contain an issues array")
        items = payload["issues"]
        start = int(payload.get("startAt", arguments.get("start_at", 0)))
        total = payload.get("total")
        next_start = start + len(items)
        more = next_start < total if isinstance(total, int) else None
        if more and not items:
            raise ValueError("Jira returned an empty page without advancing its continuation")
        return ResultPage(value=items, meta=ResultMeta(source="jira", total=total,
            has_next=more, next_arguments={**arguments, "start_at": next_start} if more else None,
            complete=not more and start == 0 if more is not None else None))
    if source_tool == "execute_sql":
        if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
            raise ValueError("SQL MCP response must contain a rows array")
        truncated = bool(payload.get("truncated"))
        return ResultPage(value=payload["rows"], meta=ResultMeta(source="sql",
            total=None if truncated else len(payload["rows"]), has_next=None if truncated else False,
            complete=not truncated, truncated=truncated, columns=payload.get("columns", [])))
    # Generic adapters preserve unknown objects, scalars and null as records.
    # Their pagination state is unknown until they publish explicit metadata.
    return ResultPage(value=payload if isinstance(payload, list) else [payload],
                      meta=ResultMeta(source=source_tool, complete=None))
