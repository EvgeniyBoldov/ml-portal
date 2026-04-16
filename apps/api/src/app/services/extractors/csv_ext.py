"""CSV extractor — renders CSV as tab-separated text."""
from __future__ import annotations

import csv
from typing import Set

from app.services.extractors.base import BaseExtractor, ExtractResult
from app.services.extractors.text import _decode_best_effort


class CsvExtractor(BaseExtractor):
    """Extracts and renders CSV files as tab-separated plain text."""

    @property
    def extensions(self) -> Set[str]:
        return {"csv"}

    @property
    def kind(self) -> str:
        return "csv"

    def extract(self, data: bytes, filename: str) -> ExtractResult:
        text, enc, warn = _decode_best_effort(data)
        out_lines = []
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(text[:10000])
        except Exception:
            dialect = csv.excel
        reader = csv.reader(text.splitlines(), dialect=dialect)
        for row in reader:
            out_lines.append("\t".join("" if v is None else str(v) for v in row))
        return ExtractResult(
            text="\n".join(out_lines),
            kind=f"csv({enc})",
            meta={"encoding": enc},
            warnings=warn,
        )
