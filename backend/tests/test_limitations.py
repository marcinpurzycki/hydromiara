"""Limitations of a Report and the confidence rule built on them."""

from datetime import date

import pytest

from app.contracts.source_data import SoilData
from app.engine.confidence import (
    WHY_COMPLETE,
    assess_confidence,
    confidence_level,
    confidence_points,
    verdict_confidences,
)
from app.engine.findings import (
    POINTS_DEFAULT,
    POINTS_DIVERGENT,
    POINTS_STAND_IN,
    ConfidenceParams,
    Finding,
    plain,
)
from app.engine.limitations import (
    PERMANENT_LIMITATIONS,
    SIMULATION_LIMITATIONS,
    limitations_of,
    report_findings,
)
from app.engine.source_limitations import TOPICS, step_down_limitation
from tests.engine_helpers import recorded_soil, recorded_weather
from tests.limitation_helpers import (
    complete_source_data,
    judge,
    limitation,
    outcome,
    own_texts,
    with_step,
    without,
)

# Words the project glossary reserves or rules out in texts for the user.
AVOIDED = ("fallback", "błąd", "ostrzeże", "dokładność", "prawdopodob", "awaryjn", "plan b")


def test_permanent_limitations_are_the_fixed_ones():
    assert [(item.affects, item.permanent) for item in PERMANENT_LIMITATIONS] == [
        ("all", True), ("all", True), ("recommendations", True), ("recommendations", True),
    ]
    texts = [item.text for item in PERMANENT_LIMITATIONS]
    assert texts[0] == "Raport nie jest urzędowym stwierdzeniem suszy rolniczej."
    assert "nadmiaru wody" in texts[1] and "podtopień" in texts[1] and "zastoisk" in texts[1]
    assert "prognozy pogody" in texts[2]
    assert "rowach" in texts[3] and "niekompletne" in texts[3]
    assert all(item.permanent for item in SIMULATION_LIMITATIONS)
    simulation = " ".join(item.text for item in SIMULATION_LIMITATIONS)
    for word in ("satelitarnych", "plonu", "opłacalności", "przydatności gleby", "zmianowania"):
        assert word in simulation


@pytest.mark.parametrize(
    ("affects", "current", "multiyear"),
    [
        ("current", "średnia", "wysoka"),
        ("multiyear", "wysoka", "średnia"),
        ("all", "średnia", "średnia"),
        ("recommendations", "wysoka", "wysoka"),
    ],
)
def test_limitation_lowers_only_the_verdict_it_concerns(affects, current, multiyear):
    _, confidences, _ = judge(complete_source_data(), source_limitations=[limitation(affects)])
    assert (confidences.current.level, confidences.multiyear.level) == (current, multiyear)
    lowered = confidences.current if current != "wysoka" else confidences.multiyear
    if "średnia" in (current, multiyear):
        assert lowered.why == "Pewność oceny obniża: Brak przykładowy."


def test_permanent_limitations_never_lower_the_confidence():
    extra = limitation("all", "Stałe ograniczenie źródła.", permanent=True)
    findings, confidences, _ = judge(complete_source_data(), source_limitations=[extra])
    assert confidences.current.level == confidences.multiyear.level == "wysoka"
    assert confidences.current.why == WHY_COMPLETE
    limitations = limitations_of(findings)
    assert limitations[0] == extra and all(item.permanent for item in limitations)


def test_levels_follow_the_sum_of_points():
    assert (POINTS_DEFAULT, POINTS_STAND_IN, POINTS_DIVERGENT) == (1, 2, 2)
    assert [confidence_level(points) for points in range(5)] == [
        "wysoka", "średnia", "średnia", "niska", "niska",
    ]
    strict = ConfidenceParams(points_for_medium=1, points_for_low=1)
    assert confidence_level(1, strict) == "niska"
    with pytest.raises(ValueError):
        ConfidenceParams(points_for_medium=3, points_for_low=2)

    three = [plain(limitation("current", f"Brak {number}.")) for number in range(3)]
    assert confidence_points(three, "current") == 3
    assert confidence_points(three, "multiyear") == 0
    assert assess_confidence("current", three[:2]).level == "średnia"
    low = assess_confidence("current", three)
    assert low.level == "niska" and low.why == "Pewność oceny obniżają: Brak 0; Brak 1; Brak 2."
    assert assess_confidence("multiyear", three).level == "wysoka"
    assert assess_confidence("current", three, params=ConfidenceParams(1, 4)).level == "średnia"


def test_not_assessed_verdict_has_the_lowest_confidence_with_the_reason():
    confidences = verdict_confidences([], current_not_assessed="Powód braku oceny.")
    assert confidences.current.level == "niska"
    assert confidences.current.why.startswith("Powód braku oceny. ")
    assert confidences.multiyear.level == "wysoka"


def test_repeated_texts_are_kept_once_at_the_first_position():
    repeated = limitation("current", "To samo zdanie.")
    findings, confidences, _ = judge(
        complete_source_data(),
        first=[repeated],
        source_limitations=[
            repeated, limitation("all", "To samo zdanie."), *PERMANENT_LIMITATIONS,
        ],
        last=[repeated, limitation("recommendations", "Na końcu.")],
    )
    assert own_texts(findings) == ["To samo zdanie.", "Na końcu."]
    assert len(findings) == 2 + len(PERMANENT_LIMITATIONS)
    assert (confidences.current.level, confidences.multiyear.level) == ("średnia", "wysoka")


def test_order_is_fixed_whatever_the_order_of_the_outcomes():
    data = without(without(without(complete_source_data(), "hydro"), "satellite"), "soil")
    data = with_step(data, "terrain", 2, "Copernicus DEM GLO-30")
    options = {
        "consistency": "rozbieżne",
        "first": [limitation("all", "Pierwsze.")],
        "source_limitations": [limitation("multiyear", "Ze źródła.")],
        "last": [limitation("recommendations", "Ostatnie.")],
    }
    findings, _, assessment = judge(data, **options)
    expected = [
        "Pierwsze.", "Sprawdzenie zgodności", "Brak danych o glebie", "Dane o ukształtowaniu",
        "Brak odczytów satelitarnych", "Brak danych o ciekach", "Ze źródła.", "Ostatnie.",
    ]
    texts = own_texts(findings)
    assert len(texts) == len(expected)
    assert all(text.startswith(start) for text, start in zip(texts, expected))
    shuffled = data.model_copy(update={"outcomes": list(reversed(data.outcomes))})
    assert report_findings(shuffled, assessment, **options) == findings


def test_days_without_weather_inside_the_series_concern_both_verdicts():
    days = recorded_weather()
    holes = {date(2019, 2, 3), date(2021, 8, 9)}
    days = [
        day.model_copy(update={"precipitation_mm": None}) if day.date == date(2017, 1, 5) else day
        for day in days
        if day.date not in holes
    ]
    findings, confidences, _ = judge(complete_source_data(days))
    (text,) = own_texts(findings)
    assert "brakuje opadu lub parowania dla 3 dni" in text and "03.09.2012" in text
    assert findings[0].limitation.affects == "all"
    assert (confidences.current.level, confidences.multiyear.level) == ("średnia", "średnia")
    assert "w danych pogodowych brakuje 3 dni" in confidences.current.why


def test_one_missing_day_before_the_date_is_worded_in_the_singular():
    days = [day for day in recorded_weather() if day.date <= date(2023, 6, 19)]
    findings, _, _ = judge(complete_source_data(days))
    (text,) = own_texts(findings)
    assert "czyli 1 dzień przed Datą analizy" in text


def test_soil_profile_covering_part_of_the_depth_is_a_limitation():
    soil = recorded_soil()
    shallow = SoilData(layers=[layer for layer in soil.layers if layer.bottom_cm <= 60])
    data = complete_source_data().model_copy(update={"soil": shallow})
    findings, confidences, assessment = judge(data)
    assert assessment.root_zone.capacity_source == "partial_soil_profile"
    (text,) = own_texts(findings)
    assert "Dane o glebie obejmują 60 cm z 100 cm" in text
    assert confidences.current.level == confidences.multiyear.level == "średnia"


def test_substitute_wording_per_data_category():
    affects = {}
    for topic in TOPICS:
        found = step_down_limitation(outcome(topic, 2, "Zamiennik"))
        affects[topic] = None if found is None else found.affects
        if found is not None:
            assert "z mniej dokładnego zamiennika (Zamiennik)" in found.text
            assert "Wpływa to na: " in found.text and not found.permanent
    assert affects == {
        "weather": "all", "soil": "all", "satellite": None,
        "drought_background": "current", "terrain": "recommendations",
        "hydro": "recommendations",
    }
    assert step_down_limitation(outcome("terrain", 1)) is None
    assert step_down_limitation(outcome("terrain", None)) is None
    assert step_down_limitation(outcome("parcel", 2, "Inna usługa")) is None


def test_texts_keep_to_the_project_glossary():
    days = [day for day in recorded_weather() if date(2016, 1, 1) <= day.date <= date(2023, 6, 1)]
    data = complete_source_data(days[:900] + days[905:])
    for topic in ("soil", "terrain", "hydro", "satellite", "drought_background"):
        data = without(data, topic)
    data = with_step(data, "weather", 2, "Zamiennik")
    findings, confidences, _ = judge(data, consistency="rozbieżne")
    texts = [item.text for item in limitations_of(findings)]
    texts += [confidences.current.why, confidences.multiyear.why, WHY_COMPLETE]
    texts += [item.text for item in SIMULATION_LIMITATIONS]
    texts += [
        step_down_limitation(outcome(topic, 2, "Zamiennik")).text
        for topic in ("soil", "terrain", "hydro", "drought_background")
    ]
    assert len(texts) == 10 + len(PERMANENT_LIMITATIONS) + 3 + 2 + 4
    for text in texts:
        assert text.endswith(".") and not any(word in text.lower() for word in AVOIDED), text


def test_finding_wording_defaults_to_the_text_without_the_final_period():
    assert plain(limitation("all", "Zdanie z kropką.")).wording == "Zdanie z kropką"
    assert Finding(limitation("all"), reason="krótko").wording == "krótko"
