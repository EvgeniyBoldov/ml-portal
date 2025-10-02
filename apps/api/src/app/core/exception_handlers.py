from __future__ import annotations
from fastapi import FastAPI
from .errors import install_exception_handlers as _install

def setup_exception_handlers(app: FastAPI) -> None:
    _install(app)
