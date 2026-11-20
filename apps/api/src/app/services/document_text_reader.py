from __future__ import annotations



_TEXT_EXTENSIONS = {"txt", "md", "csv", "tsv", "json", "yaml", "yml", "log", "sql", "xml", "html"}


def _detect_ext(filename: str) -> str:
    name = (filename or "").lower()
    if "." not in name:
        return ""
    return name[name.rfind(".") + 1:]

