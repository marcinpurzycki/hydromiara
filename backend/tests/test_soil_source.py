"""Soil adapter on recorded answers of the soil service."""

import asyncio
import copy
import json
from pathlib import Path

import httpx
import pytest

from app.sources import soil_params as params
from app.sources.soil import (
    NO_ANSWER_TEXT,
    NO_DATA_TEXT,
    SoilNoDataError,
    SoilSource,
    SoilSourceError,
    find_limitations,
    parse_response,
)

FIXTURES = Path(__file__).parent / "fixtures" / "soilgrids"
LAT, LON = 52.75, 18.2
BOUNDS = [(0, 5), (5, 15), (15, 30), (30, 60), (60, 100)]


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def without_values(payload: dict, properties: tuple[str, ...], positions: list[int]) -> dict:
    """The recorded answer with the given properties nulled in the given layers."""
    changed = copy.deepcopy(payload)
    for entry in changed["properties"]["layers"]:
        if entry["name"] in properties:
            for position in positions:
                entry["depths"][position]["values"]["mean"] = None
    return changed


def source_answering(payload: object, status: int = 200, seen: list | None = None) -> SoilSource:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload)

    return SoilSource(transport=httpx.MockTransport(handler))


class NeverAnswering(httpx.AsyncBaseTransport):
    """A service that accepts the request and keeps the caller waiting."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(30)
        return httpx.Response(200, json={})


def test_full_profile_is_normalised_to_conventional_units():
    data = parse_response(recorded("profile_field.json"))
    assert [(layer.top_cm, layer.bottom_cm) for layer in data.layers] == BOUNDS
    top, bottom = data.layers[0], data.layers[-1]
    assert (top.sand_pct, top.silt_pct, top.clay_pct) == (70.5, 20.3, 9.2)
    assert top.organic_carbon_g_kg == 56.8
    assert (top.water_33kpa_vol_pct, top.water_1500kpa_vol_pct) == (38.1, 8.3)
    assert (bottom.water_33kpa_vol_pct, bottom.water_1500kpa_vol_pct) == (30.1, 10.5)
    for layer in data.layers:
        assert layer.sand_pct + layer.silt_pct + layer.clay_pct == pytest.approx(100, abs=1)


def test_full_profile_carries_only_the_permanent_limitation():
    (limitation,) = find_limitations(parse_response(recorded("profile_field.json")))
    assert limitation.text == params.UNVERIFIED_CAPACITY_TEXT
    assert limitation.permanent is True
    assert limitation.affects == "all"


def test_layers_without_water_content_are_kept_and_reported():
    payload = without_values(recorded("profile_field.json"), ("wv0033",), [3, 4])
    data = parse_response(payload)
    assert len(data.layers) == 5
    assert data.layers[3].water_33kpa_vol_pct is None
    assert data.layers[3].water_1500kpa_vol_pct == 10.0
    permanent, gap = find_limitations(data)
    assert permanent.permanent is True
    assert gap.permanent is False and gap.affects == "all"
    assert "30–60 cm, 60–100 cm" in gap.text


def test_layers_without_texture_are_reported_for_recommendations():
    payload = without_values(recorded("profile_field.json"), ("sand", "soc"), [0])
    data = parse_response(payload)
    assert data.layers[0].sand_pct is None and data.layers[0].clay_pct == 9.2
    _, gap = find_limitations(data)
    assert gap.affects == "recommendations"
    assert "0–5 cm" in gap.text


def test_property_missing_from_the_answer_becomes_none():
    payload = recorded("profile_field.json")
    payload["properties"]["layers"] = [
        entry for entry in payload["properties"]["layers"] if entry["name"] != "soc"
    ]
    data = parse_response(payload)
    assert all(layer.organic_carbon_g_kg is None for layer in data.layers)
    assert data.layers[0].sand_pct == 70.5


@pytest.mark.parametrize("name", ["no_data_sea.json", "no_data_city.json"])
def test_point_without_data_is_recognised(name):
    with pytest.raises(SoilNoDataError):
        parse_response(recorded(name))


def _broken(change) -> dict:
    payload = recorded("profile_field.json")
    change(payload["properties"]["layers"][0])
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"properties": {"layers": []}},
        recorded("invalid_coordinates.json"),
        _broken(lambda entry: entry.pop("unit_measure")),
        _broken(lambda entry: entry["unit_measure"].update(d_factor=0)),
        _broken(lambda entry: entry["depths"][0]["range"].update(unit_depth="m")),
        _broken(lambda entry: entry["depths"][0]["values"].pop("mean")),
        _broken(lambda entry: entry["depths"][0]["values"].update(mean="high")),
    ],
)
def test_unreadable_answer_is_an_error(payload):
    with pytest.raises(SoilSourceError) as raised:
        parse_response(payload)
    assert not isinstance(raised.value, SoilNoDataError)


def test_request_carries_only_the_point():
    seen: list[httpx.Request] = []
    source = source_answering(recorded("profile_field.json"), seen=seen)
    result = asyncio.run(source.fetch(LAT, LON))

    (request,) = seen
    assert str(request.url).startswith(params.QUERY_URL)
    sent = request.url.params
    assert sorted(set(sent.keys())) == ["depth", "lat", "lon", "property", "value"]
    assert (sent["lat"], sent["lon"]) == ("52.75000", "18.20000")
    assert sent.get_list("property") == ["sand", "silt", "clay", "soc", "wv0033", "wv1500"]
    assert sent.get_list("depth") == ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm"]
    assert sent.get_list("value") == ["mean"]
    assert request.headers["user-agent"] == params.USER_AGENT
    assert result.data is not None


def test_fetch_describes_how_the_profile_was_obtained():
    source = source_answering(recorded("profile_field.json"))
    data, outcome, limitations = asyncio.run(source.fetch(LAT, LON))

    assert data is not None and len(data.layers) == 5
    assert outcome.topic == "soil"
    assert outcome.ok and outcome.chain_step == 1
    assert outcome.source_name == params.SOURCE_NAME
    assert outcome.data_date is None
    assert [limitation.permanent for limitation in limitations] == [True]
    assert outcome.message == params.UNVERIFIED_CAPACITY_TEXT


def test_fetch_reports_gaps_next_to_the_data():
    payload = without_values(recorded("profile_field.json"), ("wv1500",), [4])
    data, outcome, limitations = asyncio.run(source_answering(payload).fetch(LAT, LON))

    assert data is not None and outcome.ok
    assert len(limitations) == 2
    assert "60–100 cm" in outcome.message


def test_fetch_tells_a_point_without_data_from_a_failure():
    source = source_answering(recorded("no_data_sea.json"))
    data, outcome, limitations = asyncio.run(source.fetch(55.0, 18.8))

    assert data is None and limitations == []
    assert not outcome.ok
    assert outcome.chain_step is None and outcome.source_name is None
    assert outcome.message == NO_DATA_TEXT


def test_fetch_survives_a_refused_request():
    source = source_answering(recorded("invalid_coordinates.json"), status=422)
    data, outcome, limitations = asyncio.run(source.fetch(95.0, LON))

    assert data is None and limitations == []
    assert not outcome.ok
    assert outcome.message == NO_ANSWER_TEXT


@pytest.mark.parametrize(
    "failure", [httpx.ReadTimeout("slow"), httpx.ConnectError("down"), "not json", 503]
)
def test_fetch_survives_a_timeout_an_outage_and_a_non_json_answer(failure):
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(failure, Exception):
            raise failure
        if isinstance(failure, int):
            return httpx.Response(failure, text="unavailable")
        return httpx.Response(200, text=failure)

    source = SoilSource(transport=httpx.MockTransport(handler))
    with pytest.raises(SoilSourceError):
        asyncio.run(source.profile(LAT, LON))
    data, outcome, limitations = asyncio.run(source.fetch(LAT, LON))
    assert data is None and limitations == []
    assert not outcome.ok and outcome.message == NO_ANSWER_TEXT


def test_whole_request_is_cut_off_at_the_time_limit():
    source = SoilSource(transport=NeverAnswering(), timeout_s=0.05)
    data, outcome, limitations = asyncio.run(source.fetch(LAT, LON))

    assert data is None and limitations == []
    assert not outcome.ok and outcome.message == NO_ANSWER_TEXT
    assert outcome.duration_s < 5
