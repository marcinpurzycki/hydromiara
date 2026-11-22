"""Deficit causes and terrain analysis in the Report, from the builder and the whole analysis."""

from app.catalog.crops import get_crop
from app.catalog.recommendations import list_recommendations
from app.contracts.report import Report
from app.contracts.source_data import SourceData, WeatherDay
from app.engine.causes import NO_DEFICIT_SENTENCE
from app.engine.params import EngineParams
from app.orchestrator.report_builder import ReportInputs, build_report
from app.orchestrator.report_causes import causes_part, source_names
from app.sources.terrain_params import COPERNICUS_SOURCE_NAME
from tests.analysis_helpers import ANALYSIS_DATE, NOW, start, stored_source_data, wait_finished
from tests.engine_helpers import recorded_soil
from tests.limitation_helpers import outcome
from tests.terrain_helpers import FIELD, grid, plane, rectangle

CAUSE_IDS = {"precipitation", "soil", "runoff", "crop_demand"}


def data_with(terrain=None, *, soil=True, outline=FIELD, terrain_name=COPERNICUS_SOURCE_NAME) -> SourceData:
    data = stored_source_data()
    parcel = data.parcel.model_copy(update={"geometry": outline})
    outcomes = list(data.outcomes)
    if terrain is not None:
        outcomes.append(outcome("terrain", name=terrain_name))
    if soil:
        outcomes.append(outcome("soil", name="ISRIC SoilGrids 2.0"))
    return data.model_copy(
        update={
            "parcel": parcel,
            "terrain": terrain,
            "soil": recorded_soil() if soil else None,
            "outcomes": outcomes,
        }
    )


def build(data: SourceData, crop_id: str = "winter_wheat", params: EngineParams | None = None) -> Report:
    inputs = ReportInputs(
        report_id="r1", created_at=NOW, source_data=data, crop=get_crop(crop_id),
        analysis_date=ANALYSIS_DATE,
    )
    report = build_report(inputs) if params is None else build_report(inputs, params)
    assert Report.model_validate_json(report.model_dump_json()) == report
    return report


def texts(report: Report) -> list[str]:
    return [limitation.text for limitation in report.limitations]


def by_id(report: Report) -> dict:
    return {cause.id: cause for cause in report.causes}


def test_deficit_gives_four_causes_with_indicator_threshold_and_value():
    report = build(data_with(grid(plane(3.0, 45))))
    assert max(report.current_status.deficit_level, report.multiyear_susceptibility.deficit_level) >= 1
    causes = by_id(report)
    assert set(causes) == CAUSE_IDS and len(report.causes) == 4
    for cause in report.causes:
        assert cause.indicator.name and cause.indicator.threshold is not None
        assert cause.indicator.value is not None and cause.facts
        assert cause.found or cause.recommendations == []
    assert causes["soil"].indicator.value == 213 and not causes["soil"].found
    assert causes["soil"].facts[0].source == "ISRIC SoilGrids 2.0"
    assert causes["runoff"].found and causes["runoff"].indicator.value == 3.0
    assert causes["runoff"].facts[0].source == COPERNICUS_SOURCE_NAME
    assert causes["precipitation"].facts[0].source.startswith("Open-Meteo")
    assert [cause.found for cause in report.causes] == sorted(
        (cause.found for cause in report.causes), reverse=True
    )


def test_terrain_goes_to_the_map_and_the_trace():
    report = build(data_with(grid(plane(3.0, 45))))
    direction = report.map.downhill_direction
    assert (direction.label, direction.azimuth_deg) == ("północny wschód", 45)
    assert report.map.retention_sites == [] and report.map.water_objects == []
    assert [entry.rule_id for entry in report.trace] == [
        "root_zone.capacity", "current_status.level", "multiyear.deficit_years",
        "season.state", "terrain.slope", "causes.gate", "cause.precipitation", "cause.soil",
        "cause.runoff", "cause.crop_demand",
        *(f"recommendation.{entry.id}" for entry in list_recommendations()),
        "irrigation.need", "consistency_check.result",
    ]
    slope = next(entry for entry in report.trace if entry.rule_id == "terrain.slope")
    assert slope.values["slope_pct"] == 3.0 and slope.values["downhill_azimuth_deg"] == 45
    assert slope.result == "teren opada na północny wschód"


def test_surface_model_is_named_once_as_a_limitation():
    report = build(data_with(grid(plane(3.0, 45))))
    named = [text for text in texts(report) if "razem z budynkami i roślinnością" in text]
    assert len(named) == 1 and COPERNICUS_SOURCE_NAME in named[0]
    limitation = next(item for item in report.limitations if item.text == named[0])
    assert limitation.affects == "recommendations" and not limitation.permanent
    assert len(set(texts(report))) == len(report.limitations)
    other = build(data_with(grid(plane(3.0, 45)), terrain_name="GUGiK NMT 1 m"))
    assert not any("razem z budynkami" in text for text in texts(other))
    # Limitations about the terrain do not lower the confidence of a verdict.
    assert report.current_status.confidence == other.current_status.confidence


def test_missing_terrain_and_soil_are_no_data_not_found():
    report = build(data_with(None, soil=False))
    causes = by_id(report)
    for cause_id in ("soil", "runoff"):
        assert not causes[cause_id].found and causes[cause_id].indicator.value is None
        assert causes[cause_id].finding.startswith("Nie można ocenić")
    assert [cause.id for cause in report.causes][-2:] == ["soil", "runoff"]
    assert report.map.downhill_direction is None
    assert "terrain.slope" not in [entry.rule_id for entry in report.trace]
    assert sum(text.startswith("Brak danych o ukształtowaniu terenu") for text in texts(report)) == 1


def test_small_parcel_says_that_the_grid_is_too_coarse():
    report = build(data_with(grid(plane(3.0, 45)), outline=rectangle(40.0, 40.0)))
    assert by_id(report)["runoff"].indicator.value is None
    assert "za mało punktów siatki wysokości" in by_id(report)["runoff"].finding
    assert report.map.downhill_direction is None
    assert sum("za mało punktów siatki wysokości" in text for text in texts(report)) == 1


def test_flat_parcel_has_no_direction_and_says_so():
    report = build(data_with(grid(plane(0.0, 0))))
    runoff = by_id(report)["runoff"]
    assert not runoff.found and runoff.indicator.value == 0.0
    assert report.map.downhill_direction is None
    assert any("aby wskazać kierunek spływu" in text for text in texts(report))


def wet_days(data: SourceData) -> SourceData:
    """The same series with rain on every day, so no verdict shows a deficit."""
    days = [
        WeatherDay(date=day.date, precipitation_mm=10.0, et0_mm=day.et0_mm, temperature_mean_c=None)
        for day in data.weather.days
    ]
    return data.model_copy(update={"weather": data.weather.model_copy(update={"days": days})})


def test_no_deficit_means_no_causes_and_the_report_says_so():
    report = build(wet_days(data_with(grid(plane(3.0, 45)))))
    assert report.current_status.deficit_level == 0
    assert report.multiyear_susceptibility.deficit_level == 0
    assert report.causes == []
    stated = [item for item in report.limitations if item.text == NO_DEFICIT_SENTENCE]
    assert len(stated) == 1 and stated[0].affects == "recommendations"
    gate = next(entry for entry in report.trace if entry.rule_id == "causes.gate")
    assert "żaden werdykt nie wskazuje niedoboru" in gate.result
    assert not any(entry.rule_id.startswith("cause.") for entry in report.trace)
    # The terrain is still described.
    assert report.map.downhill_direction.label == "północny wschód"
    for verdict in (report.current_status, report.multiyear_susceptibility):
        assert NO_DEFICIT_SENTENCE not in verdict.confidence.why


def test_field_without_a_crop_gets_no_causes():
    report = build(data_with(grid(plane(3.0, 45))), "bare_field")
    assert report.causes == []
    assert sum("Przyczyn niedoboru nie wyznaczono" in text for text in texts(report)) == 1
    assert NO_DEFICIT_SENTENCE not in texts(report)
    assert report.map.downhill_direction is not None


def test_source_names_fall_back_to_plain_words():
    names = source_names(stored_source_data())
    assert names.weather == "Open-Meteo" and names.soil == "dane o glebie"
    part = causes_part(data_with(None, soil=False), *_assessed(data_with(None, soil=False)))
    assert part.terrain is None and part.downhill_direction is None


def _assessed(data: SourceData):
    from app.engine.assessment import assess_water

    crop = get_crop("winter_wheat")
    return assess_water(data, crop, ANALYSIS_DATE), crop


def test_whole_analysis_gives_a_valid_report_with_causes(client):
    report_id = start(client)
    assert wait_finished(client, report_id)["state"] == "done"
    report = Report.model_validate(client.get(f"/api/reports/{report_id}").json())
    assert {cause.id for cause in report.causes} == CAUSE_IDS
    assert by_id(report)["soil"].indicator.value == 213
    rule_ids = [entry.rule_id for entry in report.trace]
    assert "terrain.slope" in rule_ids and "causes.gate" in rule_ids
    assert any("razem z budynkami i roślinnością" in text for text in texts(report))
    assert not any("Przyczyn niedoboru" in text for text in texts(report))
