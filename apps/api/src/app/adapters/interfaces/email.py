
from typing import Protocol, Sequence
class EmailClient(Protocol):
    def send(self, to: Sequence[str], subject: str, text: str, html: str | None = None) -> None: ...
