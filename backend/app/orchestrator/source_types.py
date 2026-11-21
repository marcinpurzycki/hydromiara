"""Shapes shared by the source registry and the functions that call the adapters."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.contracts.analyses import SourceId
from app.contracts.report import Limitation
from app.contracts.source_data import ParcelData, SourceOutcome, SourceTopic


@dataclass(frozen=True)
class FetchContext:
    """What a source may use: the parcel and the analysis date, nothing else."""

    parcel: ParcelData
    analysis_date: date


@dataclass(frozen=True)
class SourceFetch:
    """Answer of one source: its part of the source data, how it went, what is missing."""

    data: Any | None
    outcome: SourceOutcome
    limitations: list[Limitation] = field(default_factory=list)


Fetch = Callable[[FetchContext], Awaitable[SourceFetch]]


@dataclass(frozen=True)
class SourceSpec:
    # Name of the field of `SourceData` the answer goes into.
    topic: SourceTopic
    # Identifier in the progress shown to the user; None for a source without one.
    status_id: SourceId | None
    timeout_s: float
    # Without a required source there is no Report.
    required: bool = False
    fetch: Fetch | None = None

    @property
    def connected(self) -> bool:
        return self.fetch is not None
