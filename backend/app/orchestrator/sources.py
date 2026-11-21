"""Registry of the data sources of an analysis.

The parcel comes first, because every other source needs its position. The
remaining sources are described by `SourceSpec` entries and fetched in
parallel, each with its own time limit. An entry without a `fetch` function is
a source that is known to the API contract but not used by the analysis yet;
it is reported as missing, never as done.

Connecting a source: write an `async def fetch(context) -> SourceFetch` that
calls its adapter and put it into the entry of its topic in `default_specs`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Any

from fastapi import Depends

from app.contracts.analyses import SourceId
from app.contracts.report import Limitation
from app.contracts.source_data import ParcelData, SourceOutcome, SourceTopic
from app.orchestrator import params
from app.sources.parcels import ParcelSource, get_parcel_source
from app.sources.weather import WeatherSource


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


@dataclass(frozen=True)
class AnalysisSources:
    """Everything an analysis fetches from: the parcel service and the registry."""

    parcels: ParcelSource
    specs: tuple[SourceSpec, ...]
    parcel_timeout_s: float = params.PARCEL_TIMEOUT_S


def weather_fetch(source: WeatherSource) -> Fetch:
    async def fetch(context: FetchContext) -> SourceFetch:
        parcel = context.parcel
        data, outcome, limitations = await source.fetch(
            parcel.centroid_lat, parcel.centroid_lon, context.analysis_date
        )
        return SourceFetch(data=data, outcome=outcome, limitations=list(limitations))

    return fetch


def default_specs(weather: WeatherSource) -> tuple[SourceSpec, ...]:
    """The registry in the order the progress is shown to the user."""
    return (
        SourceSpec(
            topic="weather",
            status_id="weather",
            timeout_s=params.WEATHER_TIMEOUT_S,
            required=True,
            fetch=weather_fetch(weather),
        ),
        # Not connected yet: no fetch function, so reported as missing.
        SourceSpec(topic="soil", status_id="soil", timeout_s=0.0),
        SourceSpec(topic="terrain", status_id="terrain", timeout_s=0.0),
        SourceSpec(topic="satellite", status_id="satellite", timeout_s=0.0),
        SourceSpec(topic="hydro", status_id="hydro", timeout_s=0.0),
        SourceSpec(topic="drought_background", status_id=None, timeout_s=0.0),
    )


_default_weather = WeatherSource()


def get_weather_source() -> WeatherSource:
    """Dependency of the analysis routes; tests replace it with a recorded source."""
    return _default_weather


def get_analysis_sources(
    parcels: Annotated[ParcelSource, Depends(get_parcel_source)],
    weather: Annotated[WeatherSource, Depends(get_weather_source)],
) -> AnalysisSources:
    """Dependency of the analysis routes: the sources a new analysis will use."""
    return AnalysisSources(parcels=parcels, specs=default_specs(weather))
