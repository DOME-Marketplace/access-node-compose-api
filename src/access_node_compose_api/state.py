"""In-memory state shared between the refresher and the HTTP handlers.

There is a single writer (the refresher). Both attributes always hold immutable
objects that are replaced as a whole: assigning a reference is atomic, so a
handler that reads `state.snapshot` once sees either the old snapshot or the new
one, never a mix. No lock is needed.
"""

from dataclasses import dataclass
from datetime import datetime

from .snapshot import Snapshot


@dataclass(frozen=True)
class RefreshStatus:
    last_attempt: datetime | None = None
    last_success: datetime | None = None
    last_error: str | None = None
    last_fetched_commit: str | None = None


class State:
    def __init__(self) -> None:
        self.snapshot: Snapshot | None = None
        self.status: RefreshStatus = RefreshStatus()
