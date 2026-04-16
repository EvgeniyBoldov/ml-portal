from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Set


class StageStatus(str, Enum):
    """Processing status for a RAG pipeline node."""

    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStage(str, Enum):
    """Static pipeline stages for each ingested document."""

    UPLOAD = "upload"
    EXTRACT = "extract"
    NORMALIZE = "normalize"
    CHUNK = "chunk"


VALID_TRANSITIONS: Dict[StageStatus, Set[StageStatus]] = {
    StageStatus.PENDING: {
        StageStatus.QUEUED,
        StageStatus.PROCESSING,
        StageStatus.FAILED,
        StageStatus.CANCELLED,
    },
    StageStatus.QUEUED: {
        StageStatus.PROCESSING,
        StageStatus.FAILED,
        StageStatus.CANCELLED,
    },
    StageStatus.PROCESSING: {
        StageStatus.COMPLETED,
        StageStatus.FAILED,
        StageStatus.CANCELLED,
    },
    StageStatus.COMPLETED: {StageStatus.QUEUED},
    StageStatus.FAILED: {StageStatus.QUEUED, StageStatus.CANCELLED},
    StageStatus.CANCELLED: {StageStatus.QUEUED},
}

RETRYABLE_STAGE_STATUSES = {
    StageStatus.FAILED.value,
    StageStatus.CANCELLED.value,
    StageStatus.COMPLETED.value,
    StageStatus.PENDING.value,
}

STOPPABLE_STAGE_STATUSES = {
    StageStatus.PROCESSING.value,
    StageStatus.QUEUED.value,
}


def format_stage_name(node_type: str, node_key: str) -> str:
    if node_type == "embedding":
        return f"embed.{node_key}"
    if node_type == "index":
        return f"index.{node_key}"
    return node_key


def split_stage_name(stage: str) -> tuple[str, str]:
    if stage.startswith("embed."):
        return "embedding", stage.replace("embed.", "", 1)
    if stage.startswith("index."):
        return "index", stage.replace("index.", "", 1)
    return "pipeline", stage


def is_retry_supported(stage: str) -> bool:
    return stage == "extract" or stage.startswith("embed.") or stage.startswith("index.")


def build_stage_control(
    *,
    stage: str,
    node_type: str,
    status: str,
    archived: bool,
) -> Dict[str, Any]:
    retry_supported = is_retry_supported(stage)
    can_stop = status in STOPPABLE_STAGE_STATUSES
    can_retry = (
        not archived
        and retry_supported
        and status in RETRYABLE_STAGE_STATUSES
    )
    return {
        "stage": stage,
        "node_type": node_type,
        "status": status,
        "retry_supported": retry_supported,
        "can_retry": can_retry,
        "can_stop": can_stop,
    }
