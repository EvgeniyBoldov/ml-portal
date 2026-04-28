from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


TRACE_PACK_V2 = "runtime.trace_pack.v2"


@dataclass(slots=True)
class ReplayResult:
    ok: bool
    reason: str
    first_divergence: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "first_divergence": self.first_divergence,
        }


class RuntimeReplayRunner:
    """Deterministic replay validator for runtime trace-pack payloads."""

    def __init__(self, *, allow_side_effects: bool = False) -> None:
        self.allow_side_effects = bool(allow_side_effects)

    def replay(self, trace_pack: Dict[str, Any]) -> ReplayResult:
        version = str(trace_pack.get("trace_pack_version") or "").strip()
        if version and version != TRACE_PACK_V2:
            return ReplayResult(
                ok=False,
                reason="unsupported_trace_pack_version",
                first_divergence=f"trace_pack_version={version}",
            )

        timeline = trace_pack.get("timeline")
        if not isinstance(timeline, list):
            return ReplayResult(ok=False, reason="invalid_timeline", first_divergence="timeline is not a list")
        if not self._is_sorted_timeline(timeline):
            return ReplayResult(ok=False, reason="invalid_timeline_order", first_divergence="step_number is not monotonic")

        tool_io = trace_pack.get("tool_io")
        if not isinstance(tool_io, list):
            return ReplayResult(ok=False, reason="invalid_tool_io", first_divergence="tool_io is not a list")

        destructive = self._find_destructive(tool_io)
        if destructive and not self.allow_side_effects:
            return ReplayResult(
                ok=False,
                reason="destructive_operation_blocked",
                first_divergence=f"operation={destructive}",
            )

        missing_output = self._find_missing_tool_output(tool_io)
        if missing_output:
            return ReplayResult(
                ok=False,
                reason="missing_tool_output",
                first_divergence=f"operation={missing_output}",
            )

        return ReplayResult(ok=True, reason="replay_ok")

    @staticmethod
    def _is_sorted_timeline(timeline: List[Dict[str, Any]]) -> bool:
        last = -1
        for item in timeline:
            if not isinstance(item, dict):
                return False
            value = item.get("step_number")
            if value is None:
                continue
            try:
                step = int(value)
            except (TypeError, ValueError):
                return False
            if step < last:
                return False
            last = step
        return True

    @staticmethod
    def _find_destructive(tool_io: List[Dict[str, Any]]) -> Optional[str]:
        for item in tool_io:
            if not isinstance(item, dict):
                continue
            risk_level = str(item.get("risk_level") or "").strip().lower()
            side_effects = bool(item.get("side_effects", False))
            if risk_level in {"write", "destructive"} or side_effects:
                return str(item.get("operation_slug") or item.get("tool_slug") or "unknown_operation")
        return None

    @staticmethod
    def _find_missing_tool_output(tool_io: List[Dict[str, Any]]) -> Optional[str]:
        open_calls: set[str] = set()
        for item in tool_io:
            if not isinstance(item, dict):
                continue
            step_type = str(item.get("step_type") or "").strip()
            op = str(item.get("operation_slug") or item.get("tool_slug") or "").strip()
            if not op:
                continue
            if step_type in {"operation_call", "tool_call"}:
                open_calls.add(op)
                continue
            if step_type in {"operation_result", "tool_result"}:
                output = item.get("output")
                if output is None:
                    return op
                open_calls.discard(op)
        if open_calls:
            return sorted(open_calls)[0]
        return None


def _load_trace_pack(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("trace-pack root must be object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay runtime trace-pack without side effects")
    parser.add_argument("trace_pack_path", help="Path to trace-pack JSON")
    parser.add_argument(
        "--allow-side-effects",
        action="store_true",
        help="Allow write/destructive operations in replay validation",
    )
    args = parser.parse_args()

    path = Path(args.trace_pack_path)
    trace_pack = _load_trace_pack(path)
    result = RuntimeReplayRunner(allow_side_effects=args.allow_side_effects).replay(trace_pack)
    print(json.dumps(result.as_dict(), ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
