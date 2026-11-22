"""Water adapter: reading class files, choosing objects, the substitute chain."""

import asyncio

import httpx
import pytest
from shapely import wkb
from shapely.geometry import LineString, Point, box, shape

from app.contracts.source_data import HydroData
from app.sources import hydro_params as params
from app.sources.hydro import HydroSource
from app.sources.hydro_files import WaterRow, read_county
from app.sources.hydro_select import county_of, outline_in_file_crs, select_objects
from tests.conftest import KNOWN_ID
from tests.hydro_helpers import (
    COUNTY,
    NEAR_DITCH,
    ClassFileServer,
    SlowLink,
    live_link,
    local_link,
    write_class_files,
)

# The recorded parcel in the system of the class files (metres).
OUTLINE = box(445958, 542807, 446183, 543036)


@pytest.fixture
def parcel(parcel_source):
    found, _ = asyncio.run(parcel_source.fetch(KNOWN_ID))
    return found


@pytest.fixture
def server(tmp_path) -> ClassFileServer:
    return ClassFileServer(write_class_files(tmp_path / "remote"))


def fetch(source: HydroSource, parcel):
    return asyncio.run(source.fetch(parcel.parcel_id, parcel.geometry))


def row(geometry, name=None, type_name=None) -> WaterRow:
    return WaterRow(wkb=wkb.dumps(geometry), name=name, type_name=type_name)


def test_file_coordinates_are_easting_northing_in_metres():
    # A point measured for the recorded parcel: 18.20085 E, 52.74927 N.
    moved = outline_in_file_crs(Point(18.20085, 52.74927))
    assert moved.x == pytest.approx(446075.2, abs=1.0)
    assert moved.y == pytest.approx(542924.8, abs=1.0)
    line = LineString([(446075.2, 542924.8), (446175.2, 542924.8)])
    (item,) = select_objects([(params.DITCH, row(line))], OUTLINE)
    assert item.geometry.type == "LineString"
    lon, lat = item.geometry.coordinates[0]
    assert lon == pytest.approx(18.20085, abs=2e-5) and lat == pytest.approx(52.74927, abs=2e-5)
    # 100 m to the east: longitude grows, latitude stays.
    assert item.geometry.coordinates[1][0] > lon
    assert item.geometry.coordinates[1][1] == pytest.approx(lat, abs=1e-4)


def test_objects_within_the_radius_are_kept_nearest_first_and_cut():
    far = LineString([(446900, 542900), (447000, 542900)])  # 717 m east
    edge = LineString([(446683, 542900), (446900, 542900)])  # starts exactly 500 m east
    long_stream = LineString([(440000, 543336), (450000, 543336)])  # 300 m north, 10 km long
    rows = [
        (params.WATERCOURSE, row(long_stream, "Struga", "strumień")),
        (params.DITCH, row(far)),
        (params.DITCH, row(NEAR_DITCH)),
        (params.WATER_BODY, row(box(446500, 542800, 446520, 543000), None, "woda płynąca")),
        (params.WATER_BODY, row(box(445780, 542640, 445830, 542690), None, "woda stojąca")),
        (params.DITCH, WaterRow(wkb=b"not a geometry", name=None, type_name=None)),
    ]
    found = select_objects(rows, OUTLINE)
    assert [item.kind for item in found] == [
        params.DITCH, params.WATER_BODY, params.WATERCOURSE, params.WATERCOURSE,
    ]  # fmt: skip
    assert found[2].name == "Struga" and found[1].geometry.type == "Polygon"
    cut = outline_in_file_crs(shape(found[2].geometry.model_dump()))
    # The 10 km stream is stored only where it passes the neighbourhood of the parcel.
    assert shape(found[2].geometry.model_dump()).length < 0.03 and cut is not None
    assert select_objects([(params.DITCH, row(edge))], OUTLINE, radius_m=499.0) == []
    assert len(select_objects(rows, OUTLINE, max_objects=2)) == 2


def test_county_code_comes_from_the_parcel_identifier():
    assert county_of(KNOWN_ID) == COUNTY
    assert county_of("abc") is None and county_of("04a704_2.0020.34/2") is None


def test_only_row_groups_of_the_county_are_read(tmp_path):
    directory = write_class_files(tmp_path)
    rows = read_county(directory / "OT_SWRM_L.parquet", COUNTY)
    assert len(rows) == 2 and wkb.loads(rows[0].wkb).equals(NEAR_DITCH)
    assert read_county(directory / "OT_SWKN_L.parquet", COUNTY) == []
    assert read_county(directory / "OT_SWRM_L.parquet", "9999") == []


def test_live_read_asks_only_for_pieces_of_the_class_files(server, parcel):
    source = HydroSource(links=[live_link(server)])
    data, outcome, limitations = fetch(source, parcel)
    assert outcome.ok and outcome.chain_step == 1 and outcome.topic == "hydro"
    assert outcome.source_name == params.BDOT_SOURCE_NAME and outcome.data_date == "2026-11-21"
    assert [item.kind for item in data.objects] == [
        params.DITCH, params.WATER_BODY, params.WATERCOURSE, params.WATERCOURSE,
    ]  # fmt: skip
    assert [item.name for item in data.objects][2:] == ["Struga Testowa", "Rzeka Szeroka"]
    assert HydroData.model_validate(data.model_dump()) == data
    assert [item.affects for item in limitations] == ["recommendations"] * 2
    names = {request.url.path.rsplit("/", 1)[-1] for request in server.requests}
    assert names == {f"{name}.parquet" for name, _ in params.BDOT_CLASSES}
    for request in server.requests:
        assert request.method in ("HEAD", "GET") and not request.url.query
        assert request.headers["user-agent"] == params.USER_AGENT
        assert request.method == "HEAD" or request.headers["range"].startswith("bytes=")
        sent = str(request.url) + str(dict(request.headers))
        assert "0020" not in sent and "18.2" not in sent and "52.7" not in sent


def test_broken_live_read_steps_down_to_the_local_copy(server, parcel, tmp_path):
    server.status = 503
    source = HydroSource(links=[live_link(server), local_link(tmp_path / "copy")])
    data, outcome, limitations = fetch(source, parcel)
    assert outcome.ok and outcome.chain_step == 2
    assert outcome.source_name == params.BDOT_LOCAL_SOURCE_NAME
    assert "użyto zamiennika" in outcome.message
    assert "pochodzą z kopii pobranej" in outcome.message
    assert len(data.objects) == 4 and len(limitations) == 2


@pytest.mark.parametrize("failure", [httpx.ConnectError("down"), RuntimeError("boom")])
def test_without_a_working_link_there_is_no_data_and_no_error(server, parcel, failure):
    server.failure = failure
    data, outcome, limitations = fetch(HydroSource(links=[live_link(server)]), parcel)
    assert data is None and not outcome.ok and outcome.chain_step is None
    assert outcome.message.startswith(params.NO_DATA) and limitations == []


def test_slow_link_is_cut_by_its_time_limit(parcel, tmp_path):
    data, outcome, _ = fetch(HydroSource(links=[SlowLink()]), parcel)
    assert data is None and "nie odpowiedziało w wyznaczonym czasie" in outcome.message
    stepped = fetch(HydroSource(links=[SlowLink(), local_link(tmp_path)]), parcel)
    assert stepped.outcome.chain_step == 2 and stepped.data is not None


def test_live_read_stops_when_its_deadline_has_passed(server, parcel, monkeypatch):
    link = live_link(server)
    monkeypatch.setattr(link, "timeout_s", 0.0)
    data, outcome, _ = fetch(HydroSource(links=[link]), parcel)
    assert data is None and server.requests == []
    assert "nie odpowiedziało" in outcome.message or params.READ_TOO_SLOW in outcome.message


def test_local_copy_is_part_of_the_chain_only_when_its_files_exist(tmp_path, monkeypatch):
    monkeypatch.setenv(params.LOCAL_DIR_ENV, str(tmp_path / "water"))
    source = HydroSource()
    assert [link.name for link in source.links()] == [params.BDOT_SOURCE_NAME]
    write_class_files(tmp_path / "water")
    assert [link.name for link in source.links()] == [
        params.BDOT_SOURCE_NAME, params.BDOT_LOCAL_SOURCE_NAME,
    ]  # fmt: skip
    (tmp_path / "water" / "OT_SWKN_L.parquet").unlink()
    assert len(source.links()) == 1


def test_parcel_without_a_county_code_or_outline_gets_no_data(parcel):
    source = HydroSource(links=[SlowLink()])
    for parcel_id, geometry in (("x", parcel.geometry), (KNOWN_ID, {"type": "Nonsense"})):
        data, outcome, _ = asyncio.run(source.fetch(parcel_id, geometry))
        assert data is None and outcome.message == params.WRONG_PARCEL
