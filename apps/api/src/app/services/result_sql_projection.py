"""One top-level virtual table contract for metadata and SQL execution."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


def quote_column(name: str) -> str:
    if not name or '\x00' in name or len(name.encode('utf-8')) > 63:
        raise ValueError('Result column names must fit PostgreSQL identifiers (1–63 bytes)')
    return '"' + name.replace('"', '""') + '"'


def sql_columns(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    columns: dict[str, dict[str, Any]] = {}
    for name, field in sorted(schema.items()):
        segments = field.get('path_segments')
        if name == '$' and segments == []:
            # Scalar/list records have one value column; object records expose their own fields.
            if 'object' in field.get('types', []):
                continue
            name, segments = 'value', []
        if segments is None or len(segments) > 1:
            continue
        quote_column(name)
        types = set(field.get('types', [])) - {'null'}
        columns[name] = {'path': segments, 'type':
            'numeric' if types == {'number'} else 'boolean' if types == {'boolean'} else
            'text' if types == {'string'} else 'jsonb'}
    return columns


def schema_page(schema: dict[str, Any], *, offset: int = 0, limit: int = 20,
                query: str = '', budget: int = 2500) -> dict[str, Any]:
    columns = sql_columns(schema)
    terms = [term.strip().casefold() for term in query.split(',') if term.strip()]
    entries = [(name, column) for name, column in columns.items()
               if not terms or any(term in name.casefold() for term in terms)]
    page: dict[str, Any] = {}
    for name, column in entries[offset:offset + limit]:
        candidate = {**page, name: column}
        if len(json.dumps(candidate, ensure_ascii=False).encode()) > budget:
            break
        page = candidate
    next_offset = offset + len(page)
    more = next_offset < len(entries)
    return {'sql_columns': page, 'schema_total_columns': len(columns),
            'schema_matched_columns': len(entries), 'schema_returned_columns': len(page),
            'schema_page_complete': not more, 'schema_query': query, 'schema_offset': offset,
            'next_schema_offset': next_offset if more and page else None,
            'schema_entry_too_large': more and not page}


def sql_projection(schema: dict[str, Any], prefix: str, params: dict[str, Any]) -> str:
    parts = []
    for index, (name, column) in enumerate(sql_columns(schema).items()):
        key = f'{prefix}_path_{index}'
        params[key] = column['path']
        operator = '#>' if column['type'] == 'jsonb' else '#>>'
        value = f'(data {operator} CAST(:{key} AS text[]))'
        if column['type'] in {'numeric', 'boolean'}:
            value = f"CAST({value} AS {column['type']})"
        parts.append(f'{value} AS {quote_column(name)}')
    return ', '.join(parts)


async def inspect_table(connection: AsyncConnection, *, result_id: str,
                        schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Describe exactly the projection used by SQL, without loading records into Python."""
    params: dict[str, Any] = {'schema_result_id': result_id}
    projection = sql_projection(schema, 'schema', params)
    if not projection:
        return {}
    result = await connection.execute(text(f'SELECT {projection} FROM runtime_tool_result_rows '
        'WHERE result_id=CAST(:schema_result_id AS uuid) LIMIT 0'), params)
    description = result.cursor.description
    types = {16: 'boolean', 25: 'text', 1700: 'numeric', 3802: 'jsonb'}
    declared = sql_columns(schema)
    return {item[0]: {**declared[item[0]], 'type': types[item[1]]} for item in description}
