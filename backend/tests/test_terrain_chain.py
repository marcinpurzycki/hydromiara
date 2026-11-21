"""Terrain chain: order of links, going down the chain, time limits, no data."""

import asyncio

import pytest
from shapely.geometry import Point, Polygon, box

from app.contracts.source_data import TerrainData
from app.sources.terrain import TerrainLinkError, TerrainReading, TerrainSource

PARCEL = box(18.1995, 52.7483, 18.2025, 52.7503)


class FakeLink:
    def __init__(self, name, reading=None, error=None, delay_s=0.0, timeout_s=1.0):
        self.name, self.timeout_s = name, timeout_s
        self._reading, self._error, self._delay_s = reading, error, delay_s
        self.calls = 0

    async def read(self, outline):
        self.calls += 1
        await asyncio.sleep(self._delay_s)
        if self._error:
            raise TerrainLinkError(self._error)
        return self._reading


def reading(resolution_m: float, note: str | None = None) -> TerrainReading:
    data = TerrainData(
        resolution_m=resolution_m,
        crs="EPSG:2180",
        transform=(resolution_m, 0.0, 0.0, 0.0, -resolution_m, 0.0),
        elevations_m=[[1.0]],
    )
    return TerrainReading(data=data, data_date="2020", note=note)


def test_first_link_with_data_wins_and_later_links_are_not_asked():
    fine, coarse = FakeLink("fine", reading(1.0)), FakeLink("coarse", reading(30.0))
    data, outcome = asyncio.run(TerrainSource(links=[fine, coarse]).fetch(PARCEL))
    assert data.resolution_m == 1.0 and outcome.chain_step == 1 and outcome.source_name == "fine"
    assert outcome.message is None and outcome.data_date == "2020" and coarse.calls == 0


def test_going_down_the_chain_is_reported():
    fine = FakeLink("fine", error="usługa nie odpowiedziała")
    coarse = FakeLink("coarse", reading(30.0, note="Uwaga do odczytu."))
    data, outcome = asyncio.run(TerrainSource(links=[fine, coarse]).fetch(PARCEL))
    assert data.resolution_m == 30.0 and outcome.ok
    assert outcome.chain_step == 2 and outcome.source_name == "coarse"
    assert "fine: usługa nie odpowiedziała" in outcome.message
    assert "użyto zamiennika: coarse" in outcome.message
    assert outcome.message.endswith("Uwaga do odczytu.")


def test_link_over_its_time_limit_is_skipped():
    slow = FakeLink("slow", reading(1.0), delay_s=1.0, timeout_s=0.01)
    coarse = FakeLink("coarse", reading(30.0))
    data, outcome = asyncio.run(TerrainSource(links=[slow, coarse]).fetch(PARCEL))
    assert outcome.chain_step == 2 and "w wyznaczonym czasie" in outcome.message
    assert outcome.duration_s < 0.5


def test_no_link_with_data_gives_no_data_with_reasons():
    links = [FakeLink("fine", error="powód pierwszy"), FakeLink("coarse", error="powód drugi")]
    data, outcome = asyncio.run(TerrainSource(links=links).fetch(PARCEL))
    assert data is None and not outcome.ok and outcome.chain_step is None
    assert "fine: powód pierwszy." in outcome.message
    assert "coarse: powód drugi." in outcome.message


@pytest.mark.parametrize("geometry", [Point(18.2, 52.75), {"type": "Nothing"}, Polygon(), None])
def test_outline_that_is_not_a_polygon_gives_no_data(geometry):
    link = FakeLink("fine", reading(1.0))
    data, outcome = asyncio.run(TerrainSource(links=[link]).fetch(geometry))
    assert data is None and not outcome.ok and link.calls == 0
    assert "nie jest wielokątem" in outcome.message
