from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import closing
from typing import Any

import psycopg
from fastapi import FastAPI, Header, HTTPException, Request, Response

from helpers.secret_broker import SecretBrokerClient, extract_credential_access


app = FastAPI(title="SQL MCP Shim", version="1.1.0")

DB_DSN = os.environ.get("DB_DSN", "")
DB_READONLY = os.environ.get("DB_READONLY", "true").lower() == "true"
DB_MAX_ROWS = int(os.environ.get("DB_MAX_ROWS", "200"))
BROKER_TIMEOUT_SECONDS = int(os.environ.get("MCP_SECRET_BROKER_TIMEOUT_SECONDS", "10"))
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "dbhub-mcp-shim", "version": "1.1.0"}
SESSIONS: set[str] = set()

READONLY_SQL_RE = re.compile(r"^\s*(select|with|explain)\b", re.IGNORECASE | re.DOTALL)
LIMIT_RE = re.compile(r"\blimit\s+\d+\b", re.IGNORECASE)


def _jsonrpc_ok(rpc_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _jsonrpc_err(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _normalize_sql(sql: str, limit: int | None) -> str:
    normalized = (sql or "").strip().rstrip(";")
    if not READONLY_SQL_RE.match(normalized):
        raise ValueError("Only read-only SELECT/WITH/EXPLAIN statements are allowed")
    if limit and not LIMIT_RE.search(normalized) and normalized.lower().startswith(("select", "with")):
        normalized = f"{normalized} LIMIT {int(limit)}"
    return normalized


def _extract_dsn_from_payload(payload: dict[str, Any]) -> str:
    for key in ("db_dsn", "dsn", "database_url", "db_url"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError(
        "Resolved credential payload does not contain DSN "
        "(expected one of: db_dsn, dsn, database_url, db_url)"
    )


async def _resolve_runtime_dsn(arguments: dict[str, Any]) -> str:
    # Explicit per-call DSN has highest priority for admin/runtime discovery flows.
    for key in ("db_dsn", "dsn", "database_url", "db_url"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    access = extract_credential_access(arguments)
    if access:
        broker = SecretBrokerClient(timeout_s=BROKER_TIMEOUT_SECONDS)
        resolved = await broker.resolve(access)
        return _extract_dsn_from_payload(resolved.payload)
    if DB_DSN:
        return DB_DSN
    raise ValueError("No database DSN provided: missing credential_access and DB_DSN env")


def _run_query(dsn: str, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
    with closing(psycopg.connect(dsn)) as conn:
        if DB_READONLY:
            conn.execute("SET default_transaction_read_only = on")
        conn.execute("SET statement_timeout = '15000'")
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                return [], []
            columns = [desc.name for desc in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchmany(DB_MAX_ROWS + 1)]
            return columns, rows


def _search_objects(
    dsn: str,
    query: str,
    schema: str | None,
    object_types: list[str] | None,
    limit: int,
) -> dict[str, Any]:
    like = f"%{(query or '').strip()}%"
    kinds = set((object_types or ["table", "view", "column"]))
    clauses: list[str] = []
    params: list[Any] = []

    if "table" in kinds or "view" in kinds:
        clauses.append(
            """
            SELECT table_schema AS schema_name,
                   table_name AS object_name,
                   table_type AS object_type,
                   NULL::text AS parent_name
            FROM information_schema.tables
            WHERE (table_name ILIKE %s OR table_schema ILIKE %s)
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            """
        )
        params.extend([like, like])

    if "column" in kinds:
        clauses.append(
            """
            SELECT table_schema AS schema_name,
                   column_name AS object_name,
                   'COLUMN' AS object_type,
                   table_name AS parent_name
            FROM information_schema.columns
            WHERE (column_name ILIKE %s OR table_name ILIKE %s OR table_schema ILIKE %s)
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            """
        )
        params.extend([like, like, like])

    if not clauses:
        return {"items": []}

    sql = " UNION ALL ".join(clauses)
    if schema:
        sql = f"SELECT * FROM ({sql}) s WHERE schema_name = %s"
        params.append(schema)
    sql += " ORDER BY schema_name, object_type, object_name LIMIT %s"
    params.append(limit)

    with closing(psycopg.connect(dsn)) as conn:
        if DB_READONLY:
            conn.execute("SET default_transaction_read_only = on")
        conn.execute("SET statement_timeout = '10000'")
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [desc.name for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
    return {"items": items}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/")
async def mcp_root(
    request: Request,
    response: Response,
    mcp_session_id: str | None = Header(default=None),
) -> dict[str, Any]:
    payload = await request.json()
    rpc_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    try:
        if method == "initialize":
            session_id = str(uuid.uuid4())
            SESSIONS.add(session_id)
            response.headers["mcp-session-id"] = session_id
            return _jsonrpc_ok(
                rpc_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                    "serverInfo": SERVER_INFO,
                    "instructions": "Read-only SQL MCP shim for remote database exploration.",
                },
            )

        if not mcp_session_id or mcp_session_id not in SESSIONS:
            return _jsonrpc_err(rpc_id, -32002, "Session not initialized")

        if method == "tools/list":
            return _jsonrpc_ok(
                rpc_id,
                {
                    "tools": [
                        {
                            "name": "execute_sql",
                            "description": "Run a read-only SQL query against the remote PostgreSQL database.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "sql": {"type": "string", "description": "Read-only SQL statement"},
                                    "limit": {"type": "integer", "description": "Row limit if SQL has no LIMIT"},
                                },
                                "required": ["sql"],
                            },
                            "annotations": {
                                "readOnlyHint": True,
                                "destructiveHint": False,
                                "idempotentHint": True,
                            },
                        },
                        {
                            "name": "search_objects",
                            "description": "Search tables, views, and columns in the remote PostgreSQL schema catalog.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"},
                                    "schema": {"type": "string"},
                                    "object_types": {
                                        "type": "array",
                                        "items": {"type": "string", "enum": ["table", "view", "column"]},
                                    },
                                    "limit": {"type": "integer"},
                                },
                            },
                            "annotations": {
                                "readOnlyHint": True,
                                "destructiveHint": False,
                                "idempotentHint": True,
                            },
                        },
                    ]
                },
            )

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            dsn = await _resolve_runtime_dsn(arguments)
            if tool_name == "execute_sql":
                sql = _normalize_sql(arguments.get("sql", ""), arguments.get("limit"))
                columns, rows = _run_query(dsn, sql)
                truncated = len(rows) > DB_MAX_ROWS
                visible_rows = rows[:DB_MAX_ROWS]
                return _jsonrpc_ok(
                    rpc_id,
                    {
                        "content": [{"type": "text", "text": json.dumps(visible_rows, ensure_ascii=False, indent=2)}],
                        "structuredContent": {
                            "columns": columns,
                            "rows": visible_rows,
                            "row_count": len(visible_rows),
                            "truncated": truncated,
                            "sql": sql,
                        },
                        "isError": False,
                    },
                )
            if tool_name == "search_objects":
                result = _search_objects(
                    dsn=dsn,
                    query=arguments.get("query", ""),
                    schema=arguments.get("schema"),
                    object_types=arguments.get("object_types"),
                    limit=int(arguments.get("limit") or 50),
                )
                return _jsonrpc_ok(
                    rpc_id,
                    {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                        "structuredContent": result,
                        "isError": False,
                    },
                )
            return _jsonrpc_err(rpc_id, -32005, f"Tool '{tool_name}' not found")

        return _jsonrpc_err(rpc_id, -32601, f"Method '{method}' not found")
    except ValueError as exc:
        return _jsonrpc_ok(
            rpc_id,
            {"content": [{"type": "text", "text": str(exc)}], "isError": True},
        )
    except psycopg.Error as exc:
        return _jsonrpc_ok(
            rpc_id,
            {"content": [{"type": "text", "text": str(exc)}], "isError": True},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
