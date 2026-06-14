"""Progress events emitted by the headless export pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ExportProgress:
    """One export progress update safe to forward from a worker thread to UI."""

    stage: str
    message: str
    completed: int
    total: int = 100
    current: int | None = None
    item_total: int | None = None
    target_id: str | None = None
    composition_id: str | None = None

    @property
    def percent(self) -> int:
        if self.total <= 0:
            return 0
        return max(0, min(100, round(self.completed / self.total * 100)))


ExportProgressCallback = Callable[[ExportProgress], None]
