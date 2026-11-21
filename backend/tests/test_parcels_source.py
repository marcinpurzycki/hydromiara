"""Parcel adapter on recorded answers of the parcel service."""

import asyncio

import httpx
import pytest

from app.sources.parcel_query import ParcelQueryError, in_poland, is_parcel_id, normalize_query
from app.sources.parcels import ParcelSourceError, parse_response
from tests.conftest import KNOWN_ID, uldk_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("040704_2.0020.34/2", "040704_2.0020.34/2"),
        ("  060606_2.0014.AR_3.756 ", "060606_2.0014.AR_3.756"),
        ("Brzoza 125/3", "Brzoza 125/3"),
        ("125/3, Brzoza", "Brzoza 125/3"),
        ("Brzoza, 125/3", "Brzoza 125/3"),
        ("125/3 Brzoza", "Brzoza 125/3"),
        ("  Krusza   Podlotowa  34/2 ", "Krusza Podlotowa 34/2"),
        ("34/2, Krusza Podlotowa", "Krusza Podlotowa 34/2"),
        ("Stara Wieś 756", "Stara Wieś 756"),
    ],
)
def test_query_is_normalized_to_region_then_number(text, expected):
    assert normalize_query(text) == expected


@pytest.mark.parametrize(
    "text", ["nic", "Brzoza", "125/3", "Brzoza Wielka", "12, 13", "a, b, 3", ", 12", "ul. Polna, Brzoza"]
)
def test_query_in_unknown_form_is_rejected(text):
    with pytest.raises(ParcelQueryError):
        normalize_query(text)


def test_identifier_form():
    assert is_parcel_id("141201_1.0001.6509")
    assert not is_parcel_id("141201_1.0001")
    assert not is_parcel_id("Brzoza 125/3")


def test_point_outside_poland():
    assert in_poland(18.2, 52.75)
    assert not in_poland(13.4, 52.52)
    assert not in_poland(18.5, 55.5)


def test_parse_single_parcel_with_area_and_centroid():
    (parcel,) = parse_response(uldk_text("by_id_found.txt"))
    assert parcel.parcel_id == KNOWN_ID
    assert (parcel.number, parcel.region) == ("34/2", "Krusza Podlotowa")
    assert (parcel.commune, parcel.county) == ("Inowrocław", "powiat inowrocławski")
    assert parcel.voivodeship == "kujawsko-pomorskie"
    assert parcel.geometry.type == "Polygon"
    # Area measured in EPSG:2180, not in degrees.
    assert parcel.area_ha == pytest.approx(2.452, abs=0.001)
    assert parcel.centroid_lon == pytest.approx(18.20085, abs=1e-5)
    assert parcel.centroid_lat == pytest.approx(52.74927, abs=1e-5)


def test_parse_many_and_none():
    many = parse_response(uldk_text("search_many.txt"))
    assert len(many) == 8
    assert {parcel.number for parcel in many} == {"756"}
    assert len({parcel.parcel_id for parcel in many}) == 8
    assert parse_response(uldk_text("search_none.txt")) == []
    assert parse_response(uldk_text("not_found.txt")) == []


@pytest.mark.parametrize(
    "text", ["", "<html>Service unavailable</html>", "0\n", "1\nonly|three|fields\n", "0\na|b|c|d|e|f|SRID=4326;POLYGON((\n"]
)
def test_unreadable_answer_is_a_source_error(text):
    with pytest.raises(ParcelSourceError):
        parse_response(text)


def test_lookups_send_documented_parameters(parcel_source, uldk):
    assert asyncio.run(parcel_source.by_id(KNOWN_ID)).parcel_id == KNOWN_ID
    assert asyncio.run(parcel_source.at(18.2, 52.75)).parcel_id == KNOWN_ID
    assert len(asyncio.run(parcel_source.search("756, Stara Wieś"))) == 8

    by_id, by_xy, by_text = uldk.requests
    assert by_id["request"] == "GetParcelById" and by_id["id"] == KNOWN_ID
    assert by_xy["request"] == "GetParcelByXY" and by_xy["xy"] == "18.2,52.75,4326"
    assert by_text["request"] == "GetParcelByIdOrNr" and by_text["id"] == "Stara Wieś 756"
    for params in uldk.requests:
        assert params["srid"] == "4326"
        assert params["result"] == "id,voivodeship,county,commune,region,parcel,geom_wkt"


def test_missing_parcel_and_point_abroad(parcel_source, uldk):
    assert asyncio.run(parcel_source.by_id("040704_2.0020.99999")) is None
    assert asyncio.run(parcel_source.at(20.0, 50.0)) is None
    assert asyncio.run(parcel_source.search("Krusza Podlotowa 99999")) == []
    asked = len(uldk.requests)
    # No request is sent for a malformed identifier or a point outside Poland.
    assert asyncio.run(parcel_source.by_id("abc")) is None
    assert asyncio.run(parcel_source.at(13.4, 52.52)) is None
    assert len(uldk.requests) == asked


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), httpx.ConnectError("down"), 500])
def test_service_failure_is_a_source_error(parcel_source, uldk, failure):
    uldk.failure = failure
    with pytest.raises(ParcelSourceError):
        asyncio.run(parcel_source.by_id(KNOWN_ID))


def test_fetch_reports_how_the_parcel_was_obtained(parcel_source, uldk):
    parcel, outcome = asyncio.run(parcel_source.fetch(KNOWN_ID))
    assert parcel.parcel_id == KNOWN_ID
    assert (outcome.topic, outcome.ok, outcome.chain_step) == ("parcel", True, 1)
    assert outcome.source_name == "ULDK GUGiK"

    parcel, outcome = asyncio.run(parcel_source.fetch("040704_2.0020.99999"))
    assert parcel is None
    assert (outcome.ok, outcome.chain_step, outcome.source_name) == (False, None, None)

    uldk.failure = httpx.ReadTimeout("slow")
    parcel, outcome = asyncio.run(parcel_source.fetch(KNOWN_ID))
    assert parcel is None and not outcome.ok and outcome.message
