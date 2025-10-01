from __future__ import annotations
from fastapi import FastAPI
from typing import List, Dict, Any

def apply_openapi_overrides(app: FastAPI, *, api_version: str = "v1", server_url: str = "/api/v1") -> None:
    if app.openapi_schema:
        schema = app.openapi_schema
    else:
        schema = app.openapi()
    # info.version
    schema.setdefault("info", {}).update({"version": api_version})
    # servers
    schema["servers"] = [{"url": server_url}]
    app.openapi_schema = schema
