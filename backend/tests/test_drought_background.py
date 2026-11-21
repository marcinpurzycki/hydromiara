"""Drought background adapter: series, coverage notes and explicit absence of data.

`fixtures/edo/` holds 3x3-cell excerpts cut from the original indicator files
(all dekads of 2023, two of 2016, two of 2026), with the metadata tags removed.
"""

import asyncio
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from app.sources.drought_background import (
    SOURCE_NAME,
    DroughtBackgroundSource,
    get_drought_background_source,
    read_series,
)
from tests.drought_helpers import INSIDE, file_name, write_file, write_series

FIXTURES = Path(__file__).parent / "fixtures"
EDO = FIXTURES / "edo"
# Centre of the parcel used in the recorded dry run.
LON, LAT = 18.20085, 52.74927


def fetch(directory: Path, lon: float, lat: float, day: date):
    return asyncio.run(DroughtBackgroundSource(directory).fetch(lon, lat, day))


def test_series_matches_recorded_dry_run():
    data, outcome = fetch(EDO, LON, LAT, date(2023, 6, 20))
    recorded = json.loads((FIXTURES / "dry_run_result.json").read_text(encoding="utf-8"))["edo"]
    in_2023 = {f"{d.date:%Y%m%d}": d.cdi_class for d in data.dekads if d.date.year == 2023}

    assert in_2023 == recorded
    assert [d.date for d in data.dekads[:2]] == [date(2016, 1, 1), date(2016, 1, 11)]
    assert data.dekads[-1].date == date(2023, 6, 11)
    assert outcome.ok and outcome.chain_step == 1
    assert outcome.topic == "drought_background"
    assert outcome.source_name == SOURCE_NAME
    assert outcome.data_date == "2016-01-01/2023-06-11"


def test_series_reports_what_it_does_not_cover():
    _, outcome = fetch(EDO, LON, LAT, date(2023, 6, 20))

    assert "dostępny od 01.01.2016" in outcome.message
    assert "brakuje plików dla 250 dekad" in outcome.message
    assert "Najnowsza" not in outcome.message


@pytest.mark.parametrize("day", [date(2023, 6, 10), date(2023, 6, 11), date(2023, 12, 31)])
def test_nothing_after_the_dekad_of_the_analysis_date(day):
    data, _ = fetch(EDO, LON, LAT, day)

    assert all(d.date <= day for d in data.dekads)
    assert max(d.date for d in data.dekads).year == 2023


def test_later_files_do_not_change_the_result(tmp_path):
    day = date(2023, 6, 20)
    for path in EDO.iterdir():
        if path.name < "cdinx_m_edo_20230621":
            shutil.copy(path, tmp_path / path.name)

    assert read_series(tmp_path, LON, LAT, day) == read_series(EDO, LON, LAT, day)


def test_analysis_date_before_the_first_file_gives_no_data():
    data, outcome = fetch(EDO, LON, LAT, date(2015, 6, 15))

    assert data is None
    assert not outcome.ok
    assert outcome.chain_step is None and outcome.source_name is None
    assert outcome.data_date is None
    assert "dostępny od 01.01.2016" in outcome.message


def test_analysis_date_long_after_the_last_file_gives_no_data():
    data, outcome = fetch(EDO, LON, LAT, date(2040, 6, 15))

    assert data is None
    assert "01.11.2026" in outcome.message


def test_missing_latest_dekads_are_reported():
    data, outcome = fetch(EDO, LON, LAT, date(2026, 11, 21))

    assert data.dekads[-1].date == date(2026, 11, 1)
    assert "Najnowsza dostępna dekada wskaźnika CDI zaczyna się 01.11.2026" in outcome.message


def test_point_outside_the_grid_gives_no_data():
    data, outcome = fetch(EDO, 21.0, 52.2, date(2023, 6, 20))

    assert data is None
    assert outcome.message == "Działka leży poza zasięgiem siatki wskaźnika CDI."


def test_missing_directory_gives_no_data(tmp_path):
    data, outcome = fetch(tmp_path / "absent", LON, LAT, date(2023, 6, 20))

    assert data is None
    assert outcome.message == "Brak plików wskaźnika CDI na serwerze."


def test_complete_window_has_no_note(tmp_path):
    write_series(tmp_path, date(2013, 1, 1), date(2023, 6, 21), value=3)

    data, outcome = fetch(tmp_path, *INSIDE, date(2023, 6, 15))

    assert outcome.message is None
    assert len(data.dekads) == 10 * 36 + 17
    assert {d.cdi_class for d in data.dekads} == {3}
    assert data.dekads[0].date == date(2013, 1, 1)
    assert data.dekads[-1].date == date(2023, 6, 11)


def test_leap_day_analysis_date(tmp_path):
    write_series(tmp_path, date(2014, 1, 1), date(2024, 3, 1))

    data, outcome = fetch(tmp_path, *INSIDE, date(2024, 2, 29))

    assert data.dekads[-1].date == date(2024, 2, 21)
    assert outcome.message is None


@pytest.mark.parametrize("no_data_value", [7, 8])
def test_no_data_cells_become_none(tmp_path, no_data_value):
    write_file(tmp_path / file_name(date(2023, 6, 1)), 2)
    write_file(tmp_path / file_name(date(2023, 6, 11)), no_data_value)

    data, _ = fetch(tmp_path, *INSIDE, date(2023, 6, 15))

    assert [d.cdi_class for d in data.dekads] == [2, None]


def test_place_without_any_value_gives_no_data(tmp_path):
    write_series(tmp_path, date(2023, 5, 1), date(2023, 6, 11), value=8)

    data, outcome = fetch(tmp_path, *INSIDE, date(2023, 6, 15))

    assert data is None
    assert outcome.message == "Wskaźnik CDI nie ma wartości dla tego miejsca."


def test_unusable_files_are_counted_and_skipped(tmp_path):
    write_file(tmp_path / file_name(date(2023, 5, 21)), 1)
    (tmp_path / file_name(date(2023, 6, 1))).write_bytes(b"not a raster")
    write_file(tmp_path / file_name(date(2023, 6, 11)), 2, crs="EPSG:2180")

    data, outcome = fetch(tmp_path, *INSIDE, date(2023, 6, 15))

    assert [d.cdi_class for d in data.dekads] == [1, None, None]
    assert "Nie udało się odczytać plików wskaźnika CDI dla 2 dekad." in outcome.message


def test_only_unusable_files_give_no_data(tmp_path):
    (tmp_path / file_name(date(2023, 6, 1))).write_bytes(b"not a raster")

    data, outcome = fetch(tmp_path, *INSIDE, date(2023, 6, 15))

    assert data is None
    assert outcome.message == "Nie udało się odczytać plików wskaźnika CDI."


def test_directory_comes_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("EDO_DATA_PATH", str(tmp_path))
    assert get_drought_background_source().data_dir == tmp_path

    monkeypatch.delenv("EDO_DATA_PATH")
    assert get_drought_background_source().data_dir == Path("/data/edo")
