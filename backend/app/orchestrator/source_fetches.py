"""One function per data category that calls its adapter for an analysis.

Each returns the adapter's part of the source data, its outcome record and the
limitations that only the adapter can name. A gap that the engine names itself
from the data is left out here, so that it is not listed and counted twice.
"""

from app.orchestrator.source_types import Fetch, FetchContext, SourceFetch
from app.sources.drought_background import DroughtBackgroundSource
from app.sources.hydro import HydroSource
from app.sources.satellite import SatelliteSource
from app.sources.soil import SoilSource
from app.sources.terrain import TerrainSource
from app.sources.weather import WeatherSource


def weather_fetch(source: WeatherSource) -> Fetch:
    async def fetch(context: FetchContext) -> SourceFetch:
        parcel = context.parcel
        # The adapter also reports gaps of the series; they are left out here,
        # because the engine names the same gaps from the series itself.
        data, outcome, _ = await source.fetch(
            parcel.centroid_lat, parcel.centroid_lon, context.analysis_date
        )
        return SourceFetch(data=data, outcome=outcome)

    return fetch


def soil_fetch(source: SoilSource) -> Fetch:
    async def fetch(context: FetchContext) -> SourceFetch:
        parcel = context.parcel
        # Which soil source answered and what that means for the result is
        # named by the engine from the soil data themselves.
        data, outcome = await source.fetch(
            parcel.geometry, parcel.centroid_lon, parcel.centroid_lat
        )
        return SourceFetch(data=data, outcome=outcome)

    return fetch


def terrain_fetch(source: TerrainSource) -> Fetch:
    async def fetch(context: FetchContext) -> SourceFetch:
        # Data from a substitute further down the chain are named by the
        # engine from the chain step of the outcome.
        data, outcome = await source.fetch(context.parcel.geometry)
        return SourceFetch(data=data, outcome=outcome)

    return fetch


def satellite_fetch(source: SatelliteSource) -> Fetch:
    async def fetch(context: FetchContext) -> SourceFetch:
        data, outcome, limitations = await source.fetch(
            context.parcel.geometry, context.analysis_date
        )
        return SourceFetch(data=data, outcome=outcome, limitations=list(limitations))

    return fetch


def hydro_fetch(source: HydroSource) -> Fetch:
    async def fetch(context: FetchContext) -> SourceFetch:
        # A step down the chain is named by the engine from the outcome; the
        # adapter's limitations say what the water data cannot show.
        parcel = context.parcel
        data, outcome, limitations = await source.fetch(parcel.parcel_id, parcel.geometry)
        return SourceFetch(data=data, outcome=outcome, limitations=list(limitations))

    return fetch


def drought_background_fetch(source: DroughtBackgroundSource) -> Fetch:
    async def fetch(context: FetchContext) -> SourceFetch:
        parcel = context.parcel
        data, outcome = await source.fetch(
            parcel.centroid_lon, parcel.centroid_lat, context.analysis_date
        )
        return SourceFetch(data=data, outcome=outcome)

    return fetch
