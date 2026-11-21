"""Terrain: elevation grid around a parcel, from a chain of sources.

The chain is an ordered list of links, most accurate first. Each link either
returns a grid or says why it cannot; the first grid wins and its position in
the list is reported as the chain step. A more accurate source is added by
putting another link in front of the existing one.

Only the grid is fetched here. Slope and flow direction are computed from it
elsewhere.
"""

import time
from collections.abc import Sequence
from typing import NamedTuple, Protocol

from shapely.errors import ShapelyError
from shapely.geometry.base import BaseGeometry

from app.contracts.source_data import SourceOutcome, TerrainData
from app.sources.chain import ChainTexts, LinkFailed, no_data, run_chain
from app.sources.raster import OutlineInput, as_geometry

_TEXTS = ChainTexts(
    no_data="Nie udało się pobrać danych o ukształtowaniu terenu.",
    stepped_down=(
        "Dokładniejsze źródło wysokości terenu nie dało danych "
        "({failures}); użyto zamiennika: {name}."
    ),
)
_WRONG_OUTLINE = (
    "Obrys działki nie jest wielokątem, więc nie można wyznaczyć siatki wysokości."
)


class TerrainLinkError(LinkFailed):
    """A link has no grid for this parcel; the text says why, in Polish."""


class TerrainReading(NamedTuple):
    """What one link returns for a parcel."""

    data: TerrainData
    data_date: str | None  # day or date range the elevations refer to
    note: str | None  # shortcoming of this reading, worded for the report


class TerrainLink(Protocol):
    """One source of elevation grids in the chain."""

    name: str
    timeout_s: float

    async def read(self, outline: BaseGeometry) -> TerrainReading:
        """Grid around the outline (EPSG:4326), or TerrainLinkError."""
        ...


class TerrainFetch(NamedTuple):
    """Terrain for one analysis and how it was obtained."""

    data: TerrainData | None
    outcome: SourceOutcome


def default_links() -> list[TerrainLink]:
    """The chain used in production, most accurate link first."""
    from app.sources.terrain_copernicus import CopernicusDem30

    return [CopernicusDem30()]


class TerrainSource:
    """Elevation grid for a parcel from the first link that has one."""

    def __init__(self, links: Sequence[TerrainLink] | None = None) -> None:
        self._links = list(links) if links is not None else default_links()

    async def fetch(self, geometry: OutlineInput) -> TerrainFetch:
        """Grid around the parcel outline given in EPSG:4326, with its outcome record."""
        started = time.monotonic()
        try:
            outline = as_geometry(geometry)
        except (TypeError, ValueError, KeyError, AttributeError, ShapelyError):
            outline = None
        if outline is None or outline.is_empty or outline.geom_type not in (
            "Polygon",
            "MultiPolygon",
        ):
            return TerrainFetch(None, no_data("terrain", _WRONG_OUTLINE, started))

        result = await run_chain("terrain", self._links, outline, texts=_TEXTS)
        return TerrainFetch(result.data, result.outcome)


def get_terrain_source() -> TerrainSource:
    """Source with the production chain."""
    return TerrainSource()
