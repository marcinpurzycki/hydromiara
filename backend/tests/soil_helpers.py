"""Both soil services as recorded, for tests without network.

The category map was recorded at the lattice points of the recorded parcel
(category III at 23 of 25 points, organic soil at 2); the texture maps at its
centre ("field") and at a point in a city centre, where they hold no data
("city"). A request the recording does not cover gets 404.
"""

import asyncio
import json
from pathlib import Path

import httpx

from app.contracts.source_data import DroughtCategoryShare, SoilData, UnclassifiedArea
from app.sources import soil_params as params
from app.sources.soil import SoilSource
from app.sources.soil_category import parse_map_value, shares
from app.sources.soil_texture import cell_value, layers_from, map_coordinates

FIXTURES = Path(__file__).parent / "fixtures"
CATEGORY_HOST = "sgeo.iung.pl"
TEXTURE_HOST = "maps.isric.org"
# Centre of the recorded parcel, the point the "field" texture was recorded for.
FIELD_CENTRE = (18.20085436232132, 52.74926592298579)


def point_answer(name: str) -> dict:
    """Recorded answer of the category map for one point: forest, sea, city, organic."""
    return json.loads((FIXTURES / "iung" / f"point_{name}.json").read_text(encoding="utf-8"))


def category_answer(value: int) -> dict:
    """An answer of the category map in the recorded shape, with the given map value."""
    answer = point_answer("forest")
    answer["features"][0]["properties"]["GRAY_INDEX"] = value
    return answer


def parcel_answers() -> dict[str, dict]:
    """Recorded answers for the lattice points of the recorded parcel, by BBOX."""
    path = FIXTURES / "iung" / "parcel_field_points.json"
    return {item["bbox"]: item["answer"] for item in json.loads(path.read_text(encoding="utf-8"))}


class RecordedSoilServices(httpx.AsyncBaseTransport):
    """Answers like the two services did when the fixtures were recorded.

    `category` replaces the recorded parcel answers with one answer for every
    point; a status other than 200 makes that service fail; a host listed in
    `slow` never answers within a test.
    """

    def __init__(
        self,
        category: dict | None = None,
        category_status: int = 200,
        texture: str = "field",
        texture_status: int = 200,
        slow: tuple[str, ...] = (),
    ) -> None:
        self._category, self._category_status = category, category_status
        self._texture, self._texture_status = texture, texture_status
        self._slow = slow
        self._parcel = parcel_answers()
        self.requests: list[httpx.Request] = []

    def hosts(self) -> list[str]:
        return [request.url.host for request in self.requests]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, query = request.url.host, request.url.params
        if host in self._slow:
            await asyncio.sleep(60)
        if host == CATEGORY_HOST:
            if self._category_status != 200:
                return httpx.Response(self._category_status)
            answer = self._category or self._parcel.get(query["BBOX"])
            return httpx.Response(404) if answer is None else httpx.Response(200, json=answer)
        if host == TEXTURE_HOST and self._texture_status == 200:
            path = FIXTURES / "soilgrids_wcs" / self._texture / f"{query['COVERAGEID']}.tif"
            if path.exists():
                return httpx.Response(
                    200, content=path.read_bytes(), headers={"content-type": "image/tiff"}
                )
            return httpx.Response(404)
        return httpx.Response(self._texture_status if host == TEXTURE_HOST else 404)


def recorded_soil_source(**services) -> SoilSource:
    """The real adapter on the recorded services; arguments as RecordedSoilServices."""
    return SoilSource(transport=RecordedSoilServices(**services))


def recorded_layers(name: str = "field"):
    """Texture layers read from the recorded coverage files."""
    x, y = map_coordinates(*FIELD_CENTRE) if name == "field" else map_coordinates(21.0122, 52.2297)
    values = {}
    for prop, _ in params.TEXTURE_PROPERTIES.values():
        for depth in params.TEXTURE_DEPTHS:
            path = FIXTURES / "soilgrids_wcs" / name / f"{prop}_{depth}_mean.tif"
            values[(prop, depth)] = cell_value(path.read_bytes(), x, y)
    return layers_from(values)


def recorded_soil() -> SoilData:
    """Soil of the recorded parcel as the adapter returns it from both services."""
    categories, other = shares([parse_map_value(a) for a in parcel_answers().values()])
    return SoilData(
        layers=recorded_layers(), drought_categories=categories, unclassified_areas=other
    )


def soil_with(
    categories: dict[int, float] | None = None,
    other: dict[int, float] | None = None,
    layers: list | None = None,
    map_read: bool = True,
) -> SoilData:
    """Soil data with the given shares of categories and of other map values."""
    return SoilData(
        layers=layers or [],
        drought_categories=(
            [DroughtCategoryShare(category=c, share_pct=s) for c, s in (categories or {}).items()]
            if map_read
            else None
        ),
        unclassified_areas=(
            [UnclassifiedArea(code=c, share_pct=s) for c, s in (other or {}).items()]
            if map_read
            else None
        ),
    )
