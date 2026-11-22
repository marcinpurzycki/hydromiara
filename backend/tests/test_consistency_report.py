"""The consistency check inside the whole Report: limitations, confidence, contract."""

from datetime import date

from app.catalog.crops import get_crop
from app.contracts.report import Report
from app.contracts.source_data import (
    CdiDekad,
    DroughtBackground,
    SatelliteData,
    SatelliteScene,
)
from app.orchestrator.report_builder import ReportInputs, build_report
from tests.analysis_helpers import ANALYSIS_DATE, NOW, start, wait_finished
from tests.limitation_helpers import complete_source_data, without

DEKAD = date(2023, 6, 11)
GENERAL_MISSING = "Brak niezależnego wskaźnika suszy"


def build(source_data, crop_id: str = "winter_wheat", analysis_date: date = ANALYSIS_DATE):
    inputs = ReportInputs(
        report_id="r1",
        created_at=NOW,
        source_data=source_data,
        crop=get_crop(crop_id),
        analysis_date=analysis_date,
    )
    report = build_report(inputs)
    assert Report.model_validate_json(report.model_dump_json()) == report
    assert len({limitation.text for limitation in report.limitations}) == len(report.limitations)
    return report


def with_cdi(*dekads: tuple[date, int | None]):
    background = DroughtBackground(
        dekads=[CdiDekad(date=day, cdi_class=cdi_class) for day, cdi_class in dekads]
    )
    return complete_source_data().model_copy(update={"drought_background": background})


def own_texts(report: Report) -> list[str]:
    return [limitation.text for limitation in report.limitations if not limitation.permanent]


def test_consistent_check_leaves_the_confidence_alone():
    # Recorded weather gives a deficit on 20 June 2023; the indicator signals a drought.
    report = build(with_cdi((DEKAD, 2)))
    assert report.current_status.deficit_level > 0
    check = report.consistency_check
    assert check.result == "zgodne" and check.sentence.startswith("Zgodne.")
    assert [item.period for item in check.items] == [
        "11.06.2023–20.06.2023", "10.06.2023", "21.05.2023–20.06.2023", "wcześniejsze lata",
    ]  # fmt: skip
    assert report.current_status.label in check.sentence
    assert report.current_status.confidence.level == "wysoka"
    assert not any("Sprawdzeni" in text for text in own_texts(report))
    entry = report.trace[-1]
    assert (entry.rule_id, entry.result) == ("consistency_check.result", "zgodne")
    assert entry.values["cdi_class"] == 2
    assert entry.values["deficit_level"] == report.current_status.deficit_level


def test_divergent_check_lowers_only_the_confidence_of_the_current_status():
    report = build(with_cdi((DEKAD, 0)))
    check = report.consistency_check
    assert check.result == "rozbieżne" and check.sentence.startswith("Rozbieżne.")
    assert "wskazuje niedobór wody" in check.sentence and "nie wskazuje suszy" in check.sentence
    divergent = [text for text in own_texts(report) if "„rozbieżne”" in text]
    assert len(divergent) == 1
    limitation = next(item for item in report.limitations if item.text == divergent[0])
    assert limitation.affects == "current" and not limitation.permanent
    current = report.current_status.confidence
    assert current.level == "średnia" and "rozbieżne" in current.why
    multiyear = report.multiyear_susceptibility.confidence
    assert multiyear.level == "wysoka" and "rozbieżne" not in multiyear.why
    # The verdict itself is not changed by the check.
    assert report.current_status.deficit_level == build(with_cdi((DEKAD, 2))).current_status.deficit_level


def test_indicator_without_a_value_for_the_dekad_is_one_limitation():
    for background in (with_cdi((DEKAD, None)), with_cdi((date(2023, 6, 1), 3))):
        report = build(background)
        assert report.consistency_check.result == "brak danych"
        about = [text for text in own_texts(report) if "wskaźnik suszy" in text]
        assert len(about) == 1 and "nie ma wartości dla dekady 11.06.2023–20.06.2023" in about[0]
        current = report.current_status.confidence
        assert current.level == "średnia" and "nie ma wartości dla dekady" in current.why
        assert report.multiyear_susceptibility.confidence.level == "wysoka"


def test_transitional_class_is_named_as_a_limitation():
    report = build(with_cdi((DEKAD, 4)))
    assert report.consistency_check.result == "brak danych"
    about = [text for text in own_texts(report) if "wskaźnik suszy" in text]
    assert len(about) == 1 and "klasę przejściową (klasa 4: „powrót do normy”)" in about[0]
    assert report.current_status.confidence.level == "średnia"


def test_missing_sources_keep_their_single_general_limitation():
    data = without(without(complete_source_data(), "drought_background"), "satellite")
    report = build(data)
    check = report.consistency_check
    assert check.result == "brak danych"
    assert [item.value for item in check.items] == ["brak danych", "brak danych"]
    texts = own_texts(report)
    assert sum(text.startswith(GENERAL_MISSING) for text in texts) == 1
    assert sum(text.startswith("Brak odczytów satelitarnych") for text in texts) == 1
    assert sum("wskaźnik" in text for text in texts) == 1


def test_analysis_date_before_the_indicator_series_gets_its_own_limitation():
    data = without(complete_source_data(), "drought_background")
    report = build(data, analysis_date=date(2015, 6, 20))
    assert report.consistency_check.result == "brak danych"
    assert "dostępny od 01.01.2016" in report.consistency_check.items[0].meaning
    about = [text for text in own_texts(report) if "wskaźnik" in text]
    assert len(about) == 1 and "jest dostępny od 01.01.2016" in about[0]
    assert not any(text.startswith(GENERAL_MISSING) for text in own_texts(report))
    limitation = next(item for item in report.limitations if item.text == about[0])
    assert limitation.affects == "current"
    assert "nie sięga tak daleko wstecz" in report.current_status.confidence.why
    assert "wskaźnik" not in report.multiyear_susceptibility.confidence.why


def test_field_without_a_crop_gets_no_result_and_no_extra_limitation():
    report = build(with_cdi((DEKAD, 0)), "bare_field")
    check = report.consistency_check
    assert check.result == "brak danych"
    assert "Sprawdzenia zgodności nie wykonano: dla Pola bez uprawy" in check.sentence
    assert check.items[0].value == "klasa 0: brak suszy"
    assert "Pole bez uprawy: odczyt opisuje tylko pokrywę pola" in check.items[1].meaning
    assert not any("wskaźnik" in text or "rozbieżne" in text for text in own_texts(report))
    assert report.trace[-1].values["deficit_level"] is None


def test_data_after_the_analysis_date_do_not_change_the_report():
    base = with_cdi((date(2023, 6, 1), 1), (DEKAD, 2))
    later = base.model_copy(
        update={
            "drought_background": DroughtBackground(
                dekads=[
                    *base.drought_background.dekads,
                    CdiDekad(date=date(2023, 6, 21), cdi_class=0),
                    CdiDekad(date=date(2023, 7, 1), cdi_class=0),
                ]
            ),
            "satellite": SatelliteData(
                scenes=[
                    *base.satellite.scenes,
                    SatelliteScene(date=date(2023, 6, 21), clear_share_pct=99, ndvi=0.1, ndmi=-0.2),
                ]
            ),
        }
    )
    assert build(later).model_dump_json() == build(base).model_dump_json()
    # On an earlier date the dekad of 11-20 June is itself the future.
    earlier = build(with_cdi((date(2023, 6, 1), 0), (DEKAD, 3)), analysis_date=date(2023, 6, 19))
    assert earlier.consistency_check.items[0].period == "01.06.2023–10.06.2023"
    assert earlier.consistency_check.items[0].value == "klasa 0: brak suszy"


def test_same_inputs_give_the_same_check():
    first, second = build(with_cdi((DEKAD, 0))), build(with_cdi((DEKAD, 0)))
    assert first.consistency_check == second.consistency_check
    assert first.model_dump_json() == second.model_dump_json()


def test_check_is_made_on_the_whole_analysis_path(client):
    report_id = start(client)
    assert wait_finished(client, report_id)["state"] == "done"
    report = Report.model_validate(client.get(f"/api/reports/{report_id}").json())
    check = report.consistency_check
    # Recorded indicator files: class 2 in the dekad of 11-20 June 2023.
    assert check.result == "zgodne"
    assert [item.period for item in check.items] == [
        "11.06.2023–20.06.2023", "19.06.2023", "21.05.2023–20.06.2023", "wcześniejsze lata",
    ]  # fmt: skip
    assert check.items[0].value.startswith("klasa 2:")
    assert report.trace[-1].rule_id == "consistency_check.result"
    assert not any("Sprawdzenia zgodności" in text for text in own_texts(report))
