"""Deterministic absence normalization shared by task validation boundaries."""
from __future__ import annotations

from typing import Any



def is_absent(value: Any) -> bool:
    return value is None or isinstance(value, str) and not value.strip()


TASK_COMPLETION_RULES = """Normalization and verification rules:
completion and report are required, non-blank strings. Unknown fields and output keys are errors.
Optional envelope fields may be omitted, null, or blank: outputs -> {}, needs/coverage -> [], limitation -> null.
Every supplied output is a typed slot. Required outputs must be present for fulfilled; a missing value member is an error.
Inside value slots, null/blank text means absence: use null if the value schema permits it; otherwise a schema-valid empty string, array or object. An absent optional object property may be omitted. Required data is never invented. Zero, false, [] and {} remain values.
needs is non-empty only for completion=needs. limitation is required only for unfulfillable; absent/null/blank limitation is allowed otherwise.
needs and unfulfillable may supply partial outputs, but every supplied output must still validate.
needs refs and coverage (output_key, output_path) pairs must be unique.
Coverage proves access to data, not equality of output length to source rows: SQL can filter, group and reshape data.
If this task has any clipped stored tool result (inline_complete=false), every non-empty output array needs a coverage claim. A root claim covers all nested arrays in that value.
For SQL-derived outputs cite the saved SQL result_id and its successful SQL query_call_id. For copied select pages cite the original result_id and all successful select query_call_ids.
coverage.output_path is a dot-separated path within the value; omitted, null, or blank means the entire value. A claim also covers nested arrays. Only use observed references; SQL claims require a successfully stored complete query result; copied select claims require contiguous complete selection pages.
Source completeness is required only when the output spec sets require_complete_source=true (default false). Such outputs always require coverage referencing runtime-confirmed complete sources. Completeness of the query, source data and inline preview are different properties.
If validation fails, correct the listed paths in the same task. Do not repeat completed external actions just to repair the declaration."""
