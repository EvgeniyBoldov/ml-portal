"""Durable document commands and progress, independent of the long corpus transaction."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

from common import DATA

CURRENT_OPERATION: ContextVar[str | None] = ContextVar("hippo_operation", default=None)


@contextmanager
def connection():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / "portal-operations.sqlite", timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, document_id TEXT NOT NULL, generation INTEGER NOT NULL, action TEXT NOT NULL, record TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS document_heads (document_id TEXT PRIMARY KEY, generation INTEGER NOT NULL, operation_id TEXT NOT NULL, available INTEGER NOT NULL DEFAULT 0)")
    try:
        with db:
            yield db
    finally:
        db.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get(operation_id: str) -> dict[str, Any] | None:
    with connection() as db:
        row = db.execute("SELECT record FROM operations WHERE id=?", (operation_id,)).fetchone()
    return json.loads(row[0]) if row else None


def admit(operation_id: str, document_id: str, generation: int, action: str) -> tuple[dict, bool]:
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT record FROM operations WHERE id=?", (operation_id,)).fetchone()
        previous = json.loads(row[0]) if row else None
        if previous and (previous["document_id"], previous["generation"], previous["action"]) != (document_id, generation, action):
            raise ValueError("Operation ID belongs to different input")
        if previous and previous["status"] in {"queued", "running", "completed", "cancelled"}:
            return previous, False
        head = db.execute("SELECT generation, operation_id, available FROM document_heads WHERE document_id=?", (document_id,)).fetchone()
        stale = bool(head and (head[0] > generation or head[0] == generation and head[1] != operation_id))
        record = {"operation_id": operation_id, "document_id": document_id, "generation": generation,
                  "action": action, "status": "cancelled" if stale else "queued", "steps": {},
                  "created_at": (previous or {}).get("created_at", now()), "updated_at": now()}
        db.execute("INSERT OR REPLACE INTO operations VALUES (?,?,?,?,?)", (operation_id, document_id, generation, action, json.dumps(record)))
        if not stale:
            available = int(bool(head and head[2])) if action == "add" else 0
            db.execute("INSERT OR REPLACE INTO document_heads VALUES (?,?,?,?)", (document_id, generation, operation_id, available))
    return record, not stale


def current(operation_id: str) -> bool:
    with connection() as db:
        return db.execute("SELECT 1 FROM document_heads WHERE operation_id=?", (operation_id,)).fetchone() is not None


def update(operation_id: str, **values: Any) -> dict:
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT record FROM operations WHERE id=?", (operation_id,)).fetchone()
        record = json.loads(row[0])
        record.update(values, updated_at=now())
        db.execute("UPDATE operations SET record=? WHERE id=?", (json.dumps(record), operation_id))
    return record


def step(key: str, status: str, metrics: dict | None = None) -> None:
    operation_id = CURRENT_OPERATION.get()
    if operation_id is None:
        return
    record = get(operation_id)
    steps = record["steps"]
    previous = steps.get(key, {})
    timestamp = now()
    steps[key] = {**previous, "key": key, "status": status, "updated_at": timestamp,
                  "metrics": {**previous.get("metrics", {}), **(metrics or {})}}
    if status == "processing":
        steps[key].setdefault("started_at", timestamp)
    if status in {"completed", "failed", "cancelled"}:
        steps[key]["finished_at"] = timestamp
    update(operation_id, steps=steps)


def complete(operation_id: str, result: dict, *, available: bool) -> None:
    with connection() as db:
        db.execute("UPDATE document_heads SET available=? WHERE operation_id=?", (int(available), operation_id))
    update(operation_id, status="completed", result=result, finished_at=now())


def unavailable_documents() -> set[str]:
    with connection() as db:
        return {row[0] for row in db.execute("SELECT document_id FROM document_heads WHERE available=0")}


def recover_interrupted() -> None:
    with connection() as db:
        rows = db.execute("SELECT id,record FROM operations").fetchall()
        for operation_id, raw in rows:
            record = json.loads(raw)
            if record["status"] in {"queued", "running"}:
                record.update(status="failed", error="Worker restarted before operation completed", updated_at=now())
                db.execute("UPDATE operations SET record=? WHERE id=?", (json.dumps(record), operation_id))
