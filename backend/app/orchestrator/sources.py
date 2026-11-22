"""Registry of the data sources of an analysis.

The parcel comes first, because every other source needs its position. The
remaining sources are described by `SourceSpec` entries and fetched in
parallel, each with its own time limit. An entry without a `fetch` function is
a source that is known to the API contract but not used by the analysis yet;
it is reported as missing, never as done.

Connecting a source: write a function in `source_fetches.py` that calls its
adapter and put it into the entry of its topic in `default_specs`.

The drought background has no identifier among the sources of the progress
shown to the user, so it is fetched without a progress entry; its outcome is
stored with the source data and listed among the sources of the Report.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from app.orchestrator import params
from app.orchestrator.source_fetches import (
    drought_background_fetch,
    hydro_fetch,
    satellite_fetch,
    soil_fetch,
    terrain_fetch,
    weather_fetch,
)
from app.orchestrator.source_types import Fetch, FetchContext, SourceFetch, SourceSpec
from app.sources.drought_background import DroughtBackgroundSource
from app.sources.hydro import HydroSource
from app.sources.parcels import ParcelSource, get_parcel_source
from app.sources.satellite import SatelliteSource
from app.sources.soil import SoilSource
from app.sources.terrain import TerrainSource
from app.sources.weather import WeatherSource

__all__ = [
    "AnalysisSources",
    "Fetch",
    "FetchContext",
    "OptionalSources",
    "SourceFetch",
    "SourceSpec",
    "default_specs",
    "get_analysis_sources",
    "get_optional_sources",
    "get_weather_source",
]


@dataclass(frozen=True)
class OptionalSources:
    """Adapters an analysis can do without; None leaves the category not connected."""

    soil: SoilSource | None = None
    terrain: TerrainSource | None = None
    satellite: SatelliteSource | None = None
    hydro: HydroSource | None = None
    drought_background: DroughtBackgroundSource | None = None


@dataclass(frozen=True)
class AnalysisSources:
    """Everything an analysis fetches from: the parcel service and the registry."""

    parcels: ParcelSource
    specs: tuple[SourceSpec, ...]
    parcel_timeout_s: float = params.PARCEL_TIMEOUT_S


def _fetch(make, adapter) -> Fetch | None:
    return None if adapter is None else make(adapter)


def default_specs(
    weather: WeatherSource, optional: OptionalSources = OptionalSources()
) -> tuple[SourceSpec, ...]:
    """The registry in the order the progress is shown to the user."""
    return (
        SourceSpec(
            topic="weather",
            status_id="weather",
            timeout_s=params.WEATHER_TIMEOUT_S,
            required=True,
            fetch=weather_fetch(weather),
        ),
        SourceSpec(
            topic="soil",
            status_id="soil",
            timeout_s=params.SOIL_TIMEOUT_S + params.ADAPTER_GRACE_S,
            fetch=_fetch(soil_fetch, optional.soil),
        ),
        SourceSpec(
            topic="terrain",
            status_id="terrain",
            timeout_s=params.TERRAIN_TIMEOUT_S,
            fetch=_fetch(terrain_fetch, optional.terrain),
        ),
        SourceSpec(
            topic="satellite",
            status_id="satellite",
            timeout_s=params.SATELLITE_TIMEOUT_S,
            fetch=_fetch(satellite_fetch, optional.satellite),
        ),
        SourceSpec(
            topic="hydro",
            status_id="hydro",
            timeout_s=params.HYDRO_TIMEOUT_S,
            fetch=_fetch(hydro_fetch, optional.hydro),
        ),
        SourceSpec(
            topic="drought_background",
            status_id=None,
            timeout_s=params.DROUGHT_BACKGROUND_TIMEOUT_S,
            fetch=_fetch(drought_background_fetch, optional.drought_background),
        ),
    )


_default_weather = WeatherSource()
# One instance per process: the satellite adapter keeps its read token.
_default_soil = SoilSource(timeout_s=params.SOIL_TIMEOUT_S)
_default_terrain = TerrainSource()
_default_satellite = SatelliteSource()
# One instance per process: the water adapter reads on one connection at a time.
_default_hydro = HydroSource()


def get_weather_source() -> WeatherSource:
    """Dependency of the analysis routes; tests replace it with a recorded source."""
    return _default_weather


def get_optional_sources() -> OptionalSources:
    """Dependency of the analysis routes; tests replace it with recorded sources."""
    return OptionalSources(
        soil=_default_soil,
        terrain=_default_terrain,
        satellite=_default_satellite,
        hydro=_default_hydro,
        # Made per analysis: reads the configured directory of the drought files.
        drought_background=DroughtBackgroundSource(),
    )


def get_analysis_sources(
    parcels: Annotated[ParcelSource, Depends(get_parcel_source)],
    weather: Annotated[WeatherSource, Depends(get_weather_source)],
    optional: Annotated[OptionalSources, Depends(get_optional_sources)],
) -> AnalysisSources:
    """Dependency of the analysis routes: the sources a new analysis will use."""
    return AnalysisSources(parcels=parcels, specs=default_specs(weather, optional))
