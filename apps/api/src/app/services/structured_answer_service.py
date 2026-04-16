from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_CODE_BLOCK_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_+-]*)\n(?P<body>.*?)```", re.DOTALL)
_TABLE_RE = re.compile(r"(?:^|\n)(\|.+\|\n\|[-:\s|]+\|\n(?:\|.*\|\n?)*)", re.MULTILINE)


class StructuredAnswerService:
    """Builds structured answer blocks from assistant markdown output."""

    CONTRACT_VERSION = "answer_blocks.v1"

    def build_blocks(
        self,
        *,
        text: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        rag_sources: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []
        normalized_text = self._normalize_primary_text(text or "")
        if normalized_text:
            blocks.append({"type": "bigstring", "label": "Answer", "value": normalized_text})

        for item in _CODE_BLOCK_RE.finditer(text or ""):
            language = (item.group("lang") or "").strip() or "text"
            body = (item.group("body") or "").rstrip()
            if not body:
                continue
            blocks.append(
                {
                    "type": "code",
                    "label": f"Code ({language})",
                    "language": language,
                    "value": body,
                }
            )

        for table_markdown in self._extract_markdown_tables(text or ""):
            parsed = self._parse_markdown_table(table_markdown)
            if not parsed:
                continue
            blocks.append(
                {
                    "type": "table",
                    "label": "Table",
                    "columns": parsed["columns"],
                    "rows": parsed["rows"],
                    "raw": table_markdown.strip(),
                }
            )

        for att in attachments or []:
            url = att.get("url")
            name = att.get("file_name") or att.get("name") or "file"
            if not url:
                continue
            blocks.append(
                {
                    "type": "file",
                    "label": "Generated file",
                    "name": name,
                    "url": str(url),
                    "content_type": att.get("content_type"),
                    "size_bytes": att.get("size_bytes"),
                }
            )

        if rag_sources:
            citation_items: List[Dict[str, Any]] = []
            for source in rag_sources:
                citation_items.append(
                    {
                        "title": source.get("title") or source.get("name") or "source",
                        "uri": source.get("uri") or source.get("url"),
                        "score": source.get("score"),
                        "snippet": source.get("snippet") or source.get("text"),
                    }
                )
            blocks.append(
                {
                    "type": "citations",
                    "label": "Citations",
                    "items": citation_items,
                }
            )

        return blocks

    def build_grounding(
        self,
        *,
        rag_sources: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        sources = list(rag_sources or [])
        if not sources:
            return {"score": 0.0, "mode": "none", "citations_count": 0}
        numeric_scores = [
            float(item.get("score"))
            for item in sources
            if isinstance(item.get("score"), (int, float))
        ]
        avg_score = (sum(numeric_scores) / len(numeric_scores)) if numeric_scores else 0.0
        mode = "weak" if avg_score < 0.5 else ("medium" if avg_score < 0.8 else "strong")
        return {
            "score": round(avg_score, 4),
            "mode": mode,
            "citations_count": len(sources),
        }

    @staticmethod
    def _extract_markdown_tables(text: str) -> List[str]:
        return [item.group(1) for item in _TABLE_RE.finditer(text)]

    @staticmethod
    def _normalize_primary_text(text: str) -> str:
        stripped = _CODE_BLOCK_RE.sub("\n", text)
        stripped = _TABLE_RE.sub("\n", stripped)
        stripped = re.sub(r"\n{3,}", "\n\n", stripped)
        return stripped.strip()

    @staticmethod
    def _parse_markdown_table(table_md: str) -> Optional[Dict[str, Any]]:
        lines = [line.strip() for line in table_md.strip().splitlines() if line.strip()]
        if len(lines) < 2:
            return None
        header = StructuredAnswerService._split_table_line(lines[0])
        if not header:
            return None
        rows: List[Dict[str, Any]] = []
        for line in lines[2:]:
            parts = StructuredAnswerService._split_table_line(line)
            if not parts:
                continue
            row: Dict[str, Any] = {}
            for idx, col in enumerate(header):
                row[col] = parts[idx] if idx < len(parts) else ""
            rows.append(row)
        return {"columns": header, "rows": rows}

    @staticmethod
    def _split_table_line(line: str) -> List[str]:
        raw = line.strip().strip("|")
        if not raw:
            return []
        return [part.strip() for part in raw.split("|")]
