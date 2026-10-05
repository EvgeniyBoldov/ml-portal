"""Runtime memory subsystem.

Keep package exports lazy so importing a focused submodule (for example prompt
constants from a migration) does not initialize the full runtime and its
external-service adapters.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "FactDTO",
    "SummaryDTO",
    "TurnMemory",
]


def __getattr__(name: str) -> Any:
    if name in {"FactDTO", "SummaryDTO"}:
        module = import_module("app.runtime.memory.dto")
    elif name == "TurnMemory":
        module = import_module("app.runtime.memory.transport")
    else:
        raise AttributeError(name)

    value = getattr(module, name)
    globals()[name] = value
    return value
