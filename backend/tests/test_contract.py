"""The placeholder payloads and the trial calculation agree with the contract models."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.analyses import CropHistory
from app.contracts.report import Report
from app.contracts.source_data import SourceData
from app.mock import data

FIXTURES = Path(__file__).parent / "fixtures"
MOCK_DIR = Path(data.__file__).parent


@pytest.fixture(scope="module")
def dry_run() -> dict:
    return json.loads((FIXTURES / "dry_run_result.json").read_text(encoding="utf-8"))


def test_mock_report_matches_contract():
    raw = json.loads((MOCK_DIR / "report.json").read_text(encoding="utf-8"))
    report = Report.model_validate(raw)
    # Nothing is dropped or defaulted on the way through the model.
    assert json.loads(report.model_dump_json()).keys() == raw.keys()
    assert len(report.causes) == 4
    assert report.multiyear_susceptibility.total_years == len(
        report.multiyear_susceptibility.years
    )


def test_mock_catalog_matches_contract():
    catalog = data.catalog()
    crop_ids = {crop.id for crop in catalog.crops}
    assert len(catalog.examples) == 6
    assert {example.crop_id for example in catalog.examples} <= crop_ids
    assert {crop.crop_id for crop in catalog.simulation.others} <= crop_ids


def test_mock_report_repeats_dry_run_numbers(dry_run):
    report = data.report_for("x")
    assert report.meta.parcel.parcel_id == dry_run["parcel"]["id"]
    assert report.meta.analysis_date.isoformat() == dry_run["analysis_date"]
    assert report.current_status.deficit_level == dry_run["now"]["level"]
    assert report.current_status.details["depletion_mm"] == dry_run["now"]["depletion_mm"]
    multiyear = report.multiyear_susceptibility
    assert multiyear.deficit_years == dry_run["deficit_years"]
    assert [(y.year, y.deficit) for y in multiyear.years] == [
        (y["year"], y["deficit"]) for y in dry_run["years"]
    ]
    assert list(report.irrigation.amount_mm) == dry_run["now"]["irrigation_mm"]


def test_report_rejects_unknown_fields():
    raw = json.loads((MOCK_DIR / "report.json").read_text(encoding="utf-8"))
    raw["unexpected"] = 1
    with pytest.raises(ValidationError):
        Report.model_validate(raw)


def test_source_data_needs_only_parcel_and_weather(dry_run):
    parcel = data.catalog().parcel
    source_data = SourceData.model_validate(
        {
            "parcel": {
                **parcel.model_dump(),
                "area_ha": dry_run["parcel"]["area_ha"],
                "centroid_lon": dry_run["parcel"]["centroid"][0],
                "centroid_lat": dry_run["parcel"]["centroid"][1],
            },
            "weather": {
                "grid_lat": dry_run["meteo_grid"][0],
                "grid_lon": dry_run["meteo_grid"][1],
                "days": [
                    {
                        "date": "2023-06-20",
                        "precipitation_mm": 0.0,
                        "et0_mm": 5.1,
                        "temperature_mean_c": 21.3,
                    }
                ],
            },
        }
    )
    assert source_data.soil is None
    assert source_data.satellite is None
    assert source_data.outcomes == []


@pytest.mark.parametrize(
    "payload",
    [{}, {"years": {"2019": "maize"}, "same_every_year": True}],
)
def test_crop_history_needs_exactly_one_form(payload):
    with pytest.raises(ValidationError):
        CropHistory.model_validate(payload)


def test_crop_history_accepts_years_from_json():
    history = CropHistory.model_validate_json('{"years": {"2019": "maize"}}')
    assert history.years == {2019: "maize"}
