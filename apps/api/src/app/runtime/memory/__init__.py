"""Runtime memory subsystem.

Post-M6 this package exposes:

    New (persistent, cross-turn):
        * dto.py       — FactDTO, SummaryDTO
        * fact_store.py / summary_store.py — data access
        * fact_extractor.py / summary_compactor.py — LLM helpers
        * builder.py / writer.py — read/write orchestration
        * transport.py — TurnMemory (in-turn, ephemeral)
"""
from app.runtime.memory.dto import FactDTO, SummaryDTO
from app.runtime.memory.transport import TurnMemory

__all__ = [
    "FactDTO",
    "SummaryDTO",
    "TurnMemory",
]
