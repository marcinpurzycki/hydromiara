"""Soil of a parcel from a substitute chain of two sources.

1. The soil drought susceptibility category of the IUNG-PIB map, read at a
   lattice of parcel points. The link has data when enough points carry a
   category, or when the map marks the parcel as organic soil.
2. Texture and organic carbon of the SoilGrids maps at the parcel centre,
   from which the engine estimates a category.

The texture is asked at the same time as the category map, whichever link
ends up answering: with both at hand the engine can tell when the two sources
describe the parcel differently. How the water capacity follows from these
data is decided by the engine (`app.engine.soil_capacity`), not here.
"""

import asyncio
import contextlib
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

import httpx
from shapely.errors import ShapelyError

from app.contracts.source_data import SoilData, SoilLayer, SourceOutcome
from app.engine.soil_capacity import category_map_decides
from app.sources import soil_params as params
from app.sources.chain import TIMED_OUT, ChainTexts, LinkFailed, LinkReading, no_data, run_chain
from app.sources.raster import OutlineInput, as_geometry
from app.sources.soil_category import CategoryMap, CategoryShares
from app.sources.soil_points import Point, sample_points
from app.sources.soil_texture import TextureMaps

_TEXTS = ChainTexts(
    no_data="Nie udało się pobrać danych o glebie.",
    stepped_down=(
        "Mapa kategorii gleb nie dała kategorii dla działki ({failures}); "
        "użyto zamiennika: {name}."
    ),
)
_WRONG_OUTLINE = "Obrys działki nie jest wielokątem, więc nie można odczytać danych o glebie."
NO_CATEGORY = "mapa nie podaje kategorii gleby dla tej działki"
NO_TEXTURE_NOTE = (
    "Globalna mapa gleb nie dała uziarnienia, więc kategorii gleby nie porównano "
    "z drugim źródłem."
)


class SoilFetch(NamedTuple):
    """Soil for one analysis and how it was obtained."""

    data: SoilData | None
    outcome: SourceOutcome


@dataclass
class SoilRequest:
    """One parcel as the links see it; the links share what they have read."""

    points: Sequence[Point]
    # Texture at the parcel centre, asked when the chain starts.
    texture: asyncio.Task
    # What the category map returned, kept also when it does not decide.
    categories: CategoryShares | None = None

    def soil(self, layers: list[SoilLayer]) -> SoilData:
        categories, other = self.categories or (None, None)
        return SoilData(layers=layers, drought_categories=categories, unclassified_areas=other)


class CategoryLink:
    """Link 1: the category map, with the texture alongside when it arrives."""

    name = params.CATEGORY_SOURCE_NAME
    # The link also waits for the texture, which ends by its own limit.
    timeout_s = params.TEXTURE_TIMEOUT_S + params.CHAIN_GRACE_S

    def __init__(self, reader: CategoryMap) -> None:
        self._reader = reader

    async def read(self, request: SoilRequest) -> LinkReading[SoilData]:
        try:
            async with asyncio.timeout(params.CATEGORY_TIMEOUT_S):
                request.categories = await self._reader.read(request.points)
        except TimeoutError as exc:
            raise LinkFailed(TIMED_OUT) from exc
        if not category_map_decides(request.soil([])):
            raise LinkFailed(NO_CATEGORY)
        try:
            layers = await asyncio.shield(request.texture)
        except Exception:  # the category stands without the texture
            return LinkReading(request.soil([]), note=NO_TEXTURE_NOTE)
        return LinkReading(request.soil(layers))


class TextureLink:
    """Link 2: texture and organic carbon of the global soil maps."""

    name = params.TEXTURE_SOURCE_NAME
    timeout_s = params.TEXTURE_TIMEOUT_S

    async def read(self, request: SoilRequest) -> LinkReading[SoilData]:
        return LinkReading(request.soil(await asyncio.shield(request.texture)))


class SoilSource:
    """Soil of a parcel from the first link that has data."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = params.TIMEOUT_S,
    ) -> None:
        self._categories = CategoryMap(transport)
        self._texture = TextureMaps(transport)
        self._timeout_s = timeout_s

    async def fetch(self, geometry: OutlineInput, lon: float, lat: float) -> SoilFetch:
        """Soil for the parcel outline and its centre (EPSG:4326), with the outcome record."""
        started = time.monotonic()
        try:
            outline = as_geometry(geometry)
            if outline.is_empty or outline.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError("outline is not a polygon")
            points = sample_points(outline)
        except (TypeError, ValueError, KeyError, AttributeError, ShapelyError):
            return SoilFetch(None, no_data("soil", _WRONG_OUTLINE, started))

        texture = asyncio.ensure_future(self._texture.read(lon, lat))
        try:
            result = await run_chain(
                "soil",
                [CategoryLink(self._categories), TextureLink()],
                SoilRequest(points=points, texture=texture),
                texts=_TEXTS,
                budget_s=self._timeout_s,
            )
        finally:
            texture.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await texture
        return SoilFetch(result.data, result.outcome)
