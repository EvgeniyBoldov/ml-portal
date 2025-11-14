from __future__ import annotations

import re
import unicodedata
from typing import List

ZERO_WIDTH = (
    "\u200B"  # zero width space
    "\u200C"  # zero width non-joiner
    "\u200D"  # zero width joiner
    "\u2060"  # word joiner
    "\uFEFF"  # zero width no-break space (BOM)
)
CONTROL_CHARS = "".join(map(chr, list(range(0, 32)) + [127]))
CONTROL_RE = re.compile(f"[{re.escape(CONTROL_CHARS)}]", flags=re.UNICODE)
ZEROW_RE = re.compile(f"[{re.escape(ZERO_WIDTH)}]", flags=re.UNICODE)

PUNCT_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201A": "'", "\u201B": "'",
    "\u201C": '"', "\u201D": '"', "\u201E": '"', "\u201F": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00AD": "",  # soft hyphen
    "\u00A0": " ",  # nbsp
}
BULLET_RE = re.compile(r"^\s*([•·▪◦►▶»\-–—])\s+", re.UNICODE)
MULTISPACE_RE = re.compile(r"[ \t\f\v]+")
BLANKS_RE = re.compile(r"\n{3,}")
HYPHEN_WRAP_RE = re.compile(r"(\w)[\-­]\n(\w)", flags=re.UNICODE)
SOFT_BREAK_RE = re.compile(r"([^\S\n]*\n)(?=\S)(?<!\.\n)", flags=re.UNICODE)

def normalize_text(text: str) -> str:
    """
    Canonicalize text:
      - Unicode NFKC
      - remove zero-width/control chars
      - map fancy quotes/dashes to standard ASCII
      - fix hyphenated line wraps and soft breaks
      - normalize bullets to "- "
      - collapse spaces and blank lines
    """
    if not text:
        return ""

    t = unicodedata.normalize("NFKC", text)
    t = t.translate(str.maketrans(PUNCT_MAP))
    t = ZEROW_RE.sub("", t)
    t = CONTROL_RE.sub("", t)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = HYPHEN_WRAP_RE.sub(r"\1\2", t)
    t = SOFT_BREAK_RE.sub(" ", t)

    lines = []
    for line in t.split("\n"):
        if BULLET_RE.match(line):
            line = "- " + BULLET_RE.sub("", line, count=1).strip()
        else:
            line = line.strip()
        line = MULTISPACE_RE.sub(" ", line)
        lines.append(line)

    t = "\n".join(lines)
    t = BLANKS_RE.sub("\n\n", t)
    return t.strip()
