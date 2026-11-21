"""Progress of one running analysis, kept in memory and shown by the status route."""

from typing import Literal

from app.contracts.analyses import SourceId, SourceProgress
from app.orchestrator import params
from app.orchestrator.sources import SourceSpec

ProgressState = Literal["wait", "run", "done", "missing"]


class Progress:
    def __init__(self, specs: tuple[SourceSpec, ...]) -> None:
        self._items: dict[SourceId, SourceProgress] = {}
        for spec in specs:
            if spec.status_id is None:
                continue
            if spec.connected:
                self._items[spec.status_id] = SourceProgress(id=spec.status_id, state="wait")
            else:
                self._items[spec.status_id] = SourceProgress(
                    id=spec.status_id, state="missing", note=params.SOURCE_NOT_CONNECTED_NOTE
                )

    def set(self, status_id: SourceId | None, state: ProgressState, note: str | None = None) -> None:
        if status_id is not None:
            self._items[status_id] = SourceProgress(id=status_id, state=state, note=note)

    def close(self) -> None:
        """Nothing is fetched any more: sources that never answered are missing."""
        for item in self.snapshot():
            if item.state in ("wait", "run"):
                self.set(item.id, "missing", item.note)

    def snapshot(self) -> list[SourceProgress]:
        return list(self._items.values())
