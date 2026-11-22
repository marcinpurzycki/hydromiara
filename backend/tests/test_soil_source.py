"""Soil adapter on recorded answers of both services: queries, parsing, the chain."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from shapely import wkt
from shapely.geometry import Point, box

from app.sources import soil_params as params
from app.sources.chain import LinkFailed
from app.sources.soil import NO_TEXTURE_NOTE, SoilSource
from app.sources.soil_category import parse_map_value, point_query, shares
from app.sources.soil_points import sample_points
from app.sources.soil_texture import NO_DATA, cell_value, coverage_query, layers_from
from app.sources.soil_texture import map_coordinates
from tests.soil_helpers import (
    CATEGORY_HOST,
    FIELD_CENTRE,
    TEXTURE_HOST,
    RecordedSoilServices,
    point_answer,
    recorded_layers,
)

FIXTURES = Path(__file__).parent / "fixtures"
OUTLINE = wkt.loads(
    (FIXTURES / "uldk" / "by_id_found.txt").read_text().splitlines()[1].split("SRID=4326;")[1]
)
CITY = (21.0122, 52.2297)


def fetch(services: RecordedSoilServices, outline=OUTLINE, centre=FIELD_CENTRE, **kwargs):
    return asyncio.run(SoilSource(transport=services, **kwargs).fetch(outline, *centre))


def test_category_query_asks_for_one_map_cell_around_the_point():
    assert point_query(18.2, 52.75) == {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetFeatureInfo",
        "LAYERS": "Susza:katgl_landuse2024", "QUERY_LAYERS": "Susza:katgl_landuse2024",
        "STYLES": "", "SRS": "EPSG:4326",
        "BBOX": "18.199950,52.749950,18.200050,52.750050",
        "WIDTH": "3", "HEIGHT": "3", "X": "1", "Y": "1",
        "INFO_FORMAT": "application/json",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("name", "value"), [("forest", 11), ("city", 13), ("organic", 5), ("sea", 0)]
)
def test_map_value_of_recorded_answers(name, value):
    # The point at sea lies outside the map: the answer has no feature.
    assert parse_map_value(point_answer(name)) == value


@pytest.mark.parametrize(
    "payload",
    [{}, {"features": [{}]}, {"features": [{"properties": {"GRAY_INDEX": "III"}}]}, [], None,
     {"features": [{"properties": {"GRAY_INDEX": 2.5}}]}],
)  # fmt: skip
def test_unreadable_map_answer_fails_the_link(payload):
    with pytest.raises(LinkFailed):
        parse_map_value(payload)


def test_shares_of_categories_and_other_map_values():
    categories, other = shares([3] * 5 + [1] * 3 + [11, 0])
    assert [(c.category, c.share_pct) for c in categories] == [(3, 50.0), (1, 30.0)]
    assert [(a.code, a.share_pct) for a in other] == [(0, 10.0), (11, 10.0)]
    assert shares([]) == ([], [])


def test_parcel_is_sampled_on_a_lattice_inside_its_outline():
    points = sample_points(OUTLINE)
    assert len(points) == params.MAX_SAMPLE_POINTS == 25
    assert all(OUTLINE.contains(Point(point)) for point in points)
    assert len(set(points)) == 25
    # A square holds exactly the 5 x 5 lattice; a sliver gets one inner point.
    assert len(sample_points(box(18.0, 52.0, 18.01, 52.01))) == 25
    sliver = wkt.loads("POLYGON((18 52, 18.01 52.0000001, 18.02 52, 18 52))")
    (only,) = sample_points(sliver, limit=0)
    assert sliver.contains(Point(only))


def test_coverage_query_asks_in_the_projection_of_the_maps():
    x, y = map_coordinates(*FIELD_CENTRE)
    assert (round(x, 1), round(y, 1)) == (2475536.4, 5821478.8)
    assert coverage_query("sand", "0-5cm", x, y) == {
        "map": "/map/sand.map", "SERVICE": "WCS", "VERSION": "2.0.1",
        "REQUEST": "GetCoverage", "COVERAGEID": "sand_0-5cm_mean", "FORMAT": "image/tiff",
        "SUBSET": ["X(2474936.4,2476136.4)", "Y(5820878.8,5822078.8)"],
        "SUBSETTINGCRS": "http://www.opengis.net/def/crs/EPSG/0/152160",
        "OUTPUTCRS": "http://www.opengis.net/def/crs/EPSG/0/152160",
    }  # fmt: skip
    # Water contents are not asked for.
    names = {name for name, _ in params.TEXTURE_PROPERTIES.values()}
    assert names == {"sand", "silt", "clay", "soc"}


def test_recorded_coverages_give_texture_in_conventional_units():
    x, y = map_coordinates(*FIELD_CENTRE)
    content = (FIXTURES / "soilgrids_wcs" / "field" / "sand_0-5cm_mean.tif").read_bytes()
    assert cell_value(content, x, y) == 704
    with pytest.raises(LinkFailed):
        cell_value(b"not a raster", x, y)
    with pytest.raises(LinkFailed):  # the point lies outside the returned window
        cell_value(content, x + 5000.0, y)
    layers = recorded_layers()
    assert [(layer.top_cm, layer.bottom_cm) for layer in layers] == [
        (0, 5), (5, 15), (15, 30), (30, 60), (60, 100),
    ]  # fmt: skip
    top = layers[0]
    assert (top.sand_pct, top.silt_pct, top.clay_pct, top.organic_carbon_g_kg) == (
        70.4, 20.2, 9.3, 51.3,
    )  # fmt: skip
    assert all(layer.water_33kpa_vol_pct is None for layer in layers)


def test_masked_place_has_no_texture():
    with pytest.raises(LinkFailed, match="nie ma wartości"):
        recorded_layers("city")
    zero = {(n, d): 0 for n, _ in params.TEXTURE_PROPERTIES.values() for d in params.TEXTURE_DEPTHS}
    with pytest.raises(LinkFailed) as raised:
        layers_from(zero)
    assert str(raised.value) == NO_DATA
    one = layers_from({**zero, ("sand", "0-5cm"): 700, ("soc", "0-5cm"): 90})
    assert (one[0].sand_pct, one[0].clay_pct, one[1].sand_pct) == (70.0, 0.0, None)


def test_category_map_answers_as_the_primary_source():
    services = RecordedSoilServices()
    data, outcome = fetch(services)
    assert (outcome.ok, outcome.chain_step, outcome.source_name) == (
        True, 1, params.CATEGORY_SOURCE_NAME,
    )  # fmt: skip
    assert outcome.message is None and outcome.data_date is None
    assert [(c.category, c.share_pct) for c in data.drought_categories] == [(3, 92.0)]
    assert [(a.code, a.share_pct) for a in data.unclassified_areas] == [(5, 8.0)]
    # The texture is read alongside, for the comparison of the two sources.
    assert len(data.layers) == 5
    assert services.hosts().count(CATEGORY_HOST) == 25
    assert services.hosts().count(TEXTURE_HOST) == 20
    # Nothing but coordinates and fixed service parameters leaves the application.
    for request in services.requests:
        assert request.headers["user-agent"] == params.USER_AGENT
        assert set(request.url.params.keys()) <= set(point_query(0, 0)) | set(
            coverage_query("sand", "0-5cm", 0, 0)
        )


@pytest.mark.parametrize("name", ["forest", "city", "sea"])
def test_parcel_without_a_category_steps_down_to_texture(name):
    data, outcome = fetch(RecordedSoilServices(category=point_answer(name)))
    assert (outcome.ok, outcome.chain_step, outcome.source_name) == (
        True, 2, params.TEXTURE_SOURCE_NAME,
    )  # fmt: skip
    assert "mapa nie podaje kategorii gleby dla tej działki" in outcome.message
    assert data.drought_categories == []
    assert [a.share_pct for a in data.unclassified_areas] == [100.0]
    assert len(data.layers) == 5


def test_organic_soil_is_an_answer_of_the_category_map():
    data, outcome = fetch(RecordedSoilServices(category=point_answer("organic")))
    assert (outcome.chain_step, outcome.source_name) == (1, params.CATEGORY_SOURCE_NAME)
    assert data.drought_categories == []
    assert [(a.code, a.share_pct) for a in data.unclassified_areas] == [(5, 100.0)]


@pytest.mark.parametrize("services", [
    RecordedSoilServices(category_status=503),
    RecordedSoilServices(category={"unexpected": True}),
    RecordedSoilServices(slow=(CATEGORY_HOST,)),
])  # fmt: skip
def test_category_map_failing_or_too_slow_steps_down(services, monkeypatch):
    monkeypatch.setattr(params, "CATEGORY_TIMEOUT_S", 0.3)
    data, outcome = fetch(services)
    assert (outcome.chain_step, outcome.source_name) == (2, params.TEXTURE_SOURCE_NAME)
    # The map was not read: there are no shares, which differs from "no category".
    assert data.drought_categories is None and data.unclassified_areas is None
    assert len(data.layers) == 5
    assert outcome.duration_s < 2.0


@pytest.mark.parametrize("services", [
    RecordedSoilServices(texture_status=503),
    RecordedSoilServices(slow=(TEXTURE_HOST,)),
])  # fmt: skip
def test_category_stands_without_the_texture(services, monkeypatch):
    monkeypatch.setattr(params, "TEXTURE_TIMEOUT_S", 0.3)
    data, outcome = fetch(services)
    assert (outcome.ok, outcome.chain_step) == (True, 1)
    assert data.layers == [] and data.drought_categories[0].category == 3
    assert outcome.message == NO_TEXTURE_NOTE
    assert outcome.duration_s < 2.0


def test_no_link_with_data_ends_without_soil():
    data, outcome = fetch(RecordedSoilServices(category_status=503, texture_status=500))
    assert data is None and not outcome.ok and outcome.chain_step is None
    assert outcome.message.startswith("Nie udało się pobrać danych o glebie.")
    assert "mapa kategorii gleb nie odpowiedziała" in outcome.message
    assert "globalna mapa gleb nie odpowiedziała" in outcome.message
    city_parcel = Point(CITY).buffer(0.0005)
    services = RecordedSoilServices(category=point_answer("city"), texture="city")
    data, outcome = fetch(services, outline=city_parcel, centre=CITY)
    assert data is None
    assert "mapa nie podaje kategorii gleby dla tej działki" in outcome.message
    assert "globalna mapa gleb nie ma wartości dla tego miejsca" in outcome.message


def test_both_services_silent_end_within_the_limits(monkeypatch):
    monkeypatch.setattr(params, "CATEGORY_TIMEOUT_S", 0.2)
    monkeypatch.setattr(params, "TEXTURE_TIMEOUT_S", 0.4)
    data, outcome = fetch(RecordedSoilServices(slow=(CATEGORY_HOST, TEXTURE_HOST)))
    assert data is None and outcome.duration_s < 2.0
    assert "nie odpowiedziało w wyznaczonym czasie" in outcome.message
    # The limit of the whole chain given by the caller ends it as well.
    data, outcome = fetch(RecordedSoilServices(slow=(CATEGORY_HOST, TEXTURE_HOST)), timeout_s=0.1)
    assert data is None and outcome.duration_s < 1.0


def test_broken_transport_never_raises():
    class Raising(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise RuntimeError("boom")

    data, outcome = asyncio.run(SoilSource(transport=Raising()).fetch(OUTLINE, *FIELD_CENTRE))
    assert data is None and not outcome.ok
    assert "nie dało odpowiedzi, którą można odczytać" in outcome.message


def test_outline_that_is_not_a_polygon_gives_no_data():
    data, outcome = fetch(RecordedSoilServices(), outline=Point(FIELD_CENTRE))
    assert data is None and "nie jest wielokątem" in outcome.message
    data, outcome = fetch(RecordedSoilServices(), outline={"type": "Polygon"})
    assert data is None and not outcome.ok


def test_recorded_parcel_answers_are_real_service_answers():
    recorded = json.loads((FIXTURES / "iung" / "parcel_field_points.json").read_text())
    assert len(recorded) == 25
    assert {item["answer"]["type"] for item in recorded} == {"FeatureCollection"}
