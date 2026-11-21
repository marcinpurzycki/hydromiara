"""Table of cases: data state -> confidence of both verdicts and the limitation texts."""

from dataclasses import dataclass, field
from datetime import date, timedelta

import pytest

from app.engine.confidence import WHY_COMPLETE, WHY_NOT_ASSESSED
from app.engine.limitations import PERMANENT_LIMITATIONS, limitations_of
from tests.analysis_helpers import ANALYSIS_DATE
from tests.engine_helpers import BARE_FIELD, WHEAT, recorded_weather
from tests.limitation_helpers import complete_source_data, judge, own_texts, with_step, without

GAP_DAYS = 3


def weather_until(last: date):
    return [day for day in recorded_weather() if day.date <= last]


def weather_from(first: date):
    return [day for day in recorded_weather() if day.date >= first]


@dataclass(frozen=True)
class Case:
    data: object
    current: str
    multiyear: str
    # Fragments expected among the limitations of this analysis: text -> affects.
    texts: dict[str, str] = field(default_factory=dict)
    # Fragments expected in the justification of each confidence.
    why_current: tuple[str, ...] = ()
    why_multiyear: tuple[str, ...] = ()
    crop: object = WHEAT
    options: dict = field(default_factory=dict)


COMPLETE = complete_source_data()

CASES = {
    "complete data": Case(
        COMPLETE, "wysoka", "wysoka", why_current=(WHY_COMPLETE,), why_multiyear=(WHY_COMPLETE,)
    ),
    "no satellite": Case(
        without(COMPLETE, "satellite"), "średnia", "średnia",
        {"Brak odczytów satelitarnych dla Działki": "all"},
        ("brak odczytów satelitarnych",), ("brak odczytów satelitarnych",),
    ),
    "terrain from the substitute": Case(
        with_step(COMPLETE, "terrain", 2, "Copernicus DEM GLO-30"), "wysoka", "wysoka",
        {"terenu pochodzą z mniej dokładnego zamiennika (Copernicus DEM GLO-30)":
         "recommendations"},
        (WHY_COMPLETE,), (WHY_COMPLETE,),
    ),
    "no soil, stand-in capacity": Case(
        without(COMPLETE, "soil"), "średnia", "średnia",
        {"pojemność wodną gleby przyjęto zastępczo (150 mm": "all"},
        ("przyjęto zastępczo",), ("przyjęto zastępczo",),
    ),
    "weather ends before the analysis date": Case(
        complete_source_data(weather_until(ANALYSIS_DATE - timedelta(days=GAP_DAYS))),
        "średnia", "wysoka",
        {"Dane pogodowe kończą się 17.06.2023, czyli 3 dni przed Datą analizy (20.06.2023)":
         "current"},
        ("kończą się 3 dni przed Datą analizy",), (WHY_COMPLETE,),
    ),
    "incomplete multi-year window": Case(
        complete_source_data(weather_from(date(2016, 1, 1))), "wysoka", "średnia",
        {"oceniona z 8 zamiast 10 lat (bez danych: 2014, 2015)": "multiyear"},
        (WHY_COMPLETE,), ("Okno wieloletnie ocenione z 8 zamiast 10 lat",),
    ),
    "field without a crop": Case(
        COMPLETE, "niska", "niska",
        why_current=("Pola bez uprawy", WHY_NOT_ASSESSED),
        why_multiyear=("Pola bez uprawy", WHY_NOT_ASSESSED),
        crop=BARE_FIELD,
    ),
    "divergent consistency check": Case(
        COMPLETE, "średnia", "wysoka",
        {"Sprawdzenie zgodności dało wynik „rozbieżne”": "current"},
        ("„rozbieżne”",), (WHY_COMPLETE,),
        options={"consistency": "rozbieżne"},
    ),
    "divergent check and no satellite": Case(
        without(COMPLETE, "satellite"), "niska", "średnia",
        {"„rozbieżne”": "current", "Brak odczytów satelitarnych": "all"},
        ("„rozbieżne”", "brak odczytów satelitarnych"), ("brak odczytów satelitarnych",),
        options={"consistency": "rozbieżne"},
    ),
    "consistent check": Case(
        COMPLETE, "wysoka", "wysoka", options={"consistency": "zgodne"}
    ),
    "no soil and no satellite": Case(
        without(without(COMPLETE, "soil"), "satellite"), "niska", "niska",
        {"przyjęto zastępczo": "all", "Brak odczytów satelitarnych": "all"},
    ),
    "no independent drought indicator": Case(
        without(COMPLETE, "drought_background"), "średnia", "wysoka",
        {"Brak niezależnego wskaźnika suszy": "current"},
    ),
    "no terrain and no water objects": Case(
        without(without(COMPLETE, "terrain"), "hydro"), "wysoka", "wysoka",
        {"Brak danych o ukształtowaniu terenu": "recommendations",
         "Brak danych o ciekach, rowach i zbiornikach": "recommendations"},
    ),
}


@pytest.mark.parametrize("case", [pytest.param(case, id=name) for name, case in CASES.items()])
def test_case_gives_the_expected_confidence_and_texts(case):
    findings, confidences, _ = judge(case.data, case.crop, **case.options)
    assert (confidences.current.level, confidences.multiyear.level) == (
        case.current, case.multiyear,
    )
    own = [f.limitation for f in findings if not f.limitation.permanent]
    assert len(own) == len(case.texts), own_texts(findings)
    for fragment, affects in case.texts.items():
        matching = [limitation for limitation in own if fragment in limitation.text]
        assert len(matching) == 1, (fragment, own_texts(findings))
        assert matching[0].affects == affects
    for fragment in case.why_current:
        assert fragment in confidences.current.why
    for fragment in case.why_multiyear:
        assert fragment in confidences.multiyear.why


@pytest.mark.parametrize("case", [pytest.param(case, id=name) for name, case in CASES.items()])
def test_every_case_ends_with_the_permanent_limitations_and_repeats_nothing(case):
    findings, _, _ = judge(case.data, case.crop, **case.options)
    limitations = limitations_of(findings)
    assert tuple(limitations[-len(PERMANENT_LIMITATIONS):]) == PERMANENT_LIMITATIONS
    own = limitations[: -len(PERMANENT_LIMITATIONS)]
    assert not any(limitation.permanent for limitation in own)
    texts = [limitation.text for limitation in limitations]
    assert len(texts) == len(set(texts))


@pytest.mark.parametrize("case", [pytest.param(case, id=name) for name, case in CASES.items()])
def test_every_case_is_deterministic(case):
    first = judge(case.data, case.crop, **case.options)
    second = judge(case.data, case.crop, **case.options)
    assert first[0] == second[0] and first[1] == second[1]
