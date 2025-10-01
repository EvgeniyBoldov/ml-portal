
import sys
from ...core.config import get_settings

class StdoutEmailClient:
    def __init__(self, default_from: str | None = None):
        self._from = default_from or get_settings().EMAIL_FROM

    def send(self, to: list[str], subject: str, text: str, html: str | None = None) -> None:
        print(f"[email] from={self._from} to={to} subject={subject}\n{text}", file=sys.stderr)
