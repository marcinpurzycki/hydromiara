"""Wording of the historical course: comparison sentence, satellite notes, assumption."""

from datetime import date

import pytest

from app.engine import history_texts
from tests.engine_helpers import WHEAT, recorded_weather
from tests.history_helpers import SAME, course_of, data, years
from tests.season_helpers import SPRING

BASE = "Podatność jest liczona dla jednej Uprawy."
# Words the project glossary tells to avoid for these notions.
AVOIDED = ("płodozmian", "zmianowani", "historia suszy", "wersja raportu", "roślin", "ugór")


def section(history, **options):
    course, assessment = course_of(history, **options)
    verdict = assessment.multiyear_susceptibility
    return course, history_texts.course_section(course, verdict, WHEAT)


def notes(history, **options) -> dict[int, str]:
    return {year.year: year.satellite_note for year in section(history, **options)[1].years}


def test_comparison_gives_the_numbers_of_both_views():
    _, part = section(years(y2015="bare_field", y2016="bare_field"))
    sentence = part.comparison_sentence
    assert "wody brakowało w 8 z 8 ocenionych lat" in sentence
    assert "Bieżącej Uprawie (Pszenica ozima)" in sentence
    assert "brakowałoby w 10 z 10 lat — to Podatność wieloletnia" in sentence
    assert "nie oceniono: 2015 (Pole bez uprawy), 2016 (Pole bez uprawy)" in sentence
    assert sentence.endswith(history_texts.NOT_REPLACING)
    assert "jej nie zastępuje" in sentence


def test_comparison_says_when_both_views_agree():
    sentence = section(SAME)[1].comparison_sentence
    assert "wody brakowało w 10 z 10 lat." in sentence
    assert "W każdym roku oba ujęcia dają ten sam wynik." in sentence
    assert "nie oceniono" not in sentence


def test_comparison_names_the_years_in_which_the_views_differ():
    day = date(2023, 3, 1)
    sentence = section(years(y2013=SPRING.id), day=day)[1].comparison_sentence
    assert "wody brakowało w 10 z 10 lat." in sentence
    assert "brakowałoby w 9 z 10 lat" in sentence
    assert "Oba ujęcia różnią się w roku 2013." in sentence


def test_comparison_without_weather():
    source = data(weather=recorded_weather()[:30])
    sentence = section(SAME, source=source)[1].comparison_sentence
    assert sentence.startswith("Według Historii upraw nie dało się ocenić żadnego roku")
    assert "Podatności wieloletniej nie oceniono." in sentence


def test_year_not_assessed_is_written_as_no_deficit_with_the_reason_in_its_note():
    course, part = section(years(y2015="bare_field", y2023=SPRING.id))
    by_year = {year.year: year for year in part.years}
    assert by_year[2015].crop.id == "bare_field" and by_year[2015].deficit is False
    assert by_year[2015].satellite_note == (
        "Roku nie oceniono: dla Pola bez uprawy Stopień niedoboru nie jest wyznaczany. "
        "Brak odczytu satelitarnego z tego roku."
    )
    assert by_year[2023].satellite_note.startswith(
        "Roku nie oceniono: Okres krytyczny tej Uprawy zaczyna się po Dacie analizy. "
    )
    assert [year.year for year in part.years] == [year.year for year in course.years]


def test_satellite_notes_with_and_without_scenes():
    given = notes(years(y2022="bare_field", y2021=SPRING.id))
    assert given[2014] == history_texts.NO_SCENE
    assert given[2020] == history_texts.NO_SCENE
    assert given[2021] == (
        "Odczyt satelitarny z 12.06.2021: NDVI 0,74; NDMI 0,31. Uprawa według Historii "
        "upraw: Uprawa jara testowa; dzień odczytu wypada w jej Sezonie uprawy. Odczyt jest "
        "opisowy i nie wpływa na ocenę roku."
    )
    assert given[2022] == (
        "Roku nie oceniono: dla Pola bez uprawy Stopień niedoboru nie jest wyznaczany. "
        "Odczyt satelitarny z 14.06.2022: NDVI 0,62; NDMI 0,20. Według Historii upraw było "
        "to Pole bez uprawy, więc odczyt opisuje tylko pokrywę pola, nie niedobór wody."
    )
    assert given[2023].startswith(
        "Rok oceniony tylko do Daty analizy (20.06.2023). Odczyt satelitarny z 09.06.2023: "
        "NDVI 0,81; NDMI 0,52. Uprawa przyjęta z sezonu Daty analizy: Pszenica ozima;"
    )
    assert set(notes(SAME, source=data(satellite=False)).values()) <= {
        history_texts.NO_SCENE,
        f"Rok oceniony tylko do Daty analizy (20.06.2023). {history_texts.NO_SCENE}",
    }


def test_scene_outside_the_season_describes_only_the_cover():
    source = data()
    late = source.satellite.scenes[0].model_copy(update={"date": date(2021, 12, 5)})
    source = source.model_copy(
        update={"satellite": source.satellite.model_copy(update={"scenes": [late]})}
    )
    note = notes(SAME, source=source)[2021]
    assert "wypada poza jej Sezonem uprawy, więc odczyt opisuje tylko pokrywę pola" in note


def test_assumption_tells_the_default_from_a_confirmation_and_from_a_history():
    default = history_texts.assumption(BASE, None)
    confirmed = history_texts.assumption(BASE, course_of(SAME)[0])
    other = history_texts.assumption(BASE, course_of(years(y2015="bare_field"))[0])
    same_named = history_texts.assumption(BASE, course_of(years(y2015="winter_wheat"))[0])
    assert len({default, confirmed, other, same_named}) == 4
    assert all(text.startswith(BASE) for text in (default, confirmed, other, same_named))
    assert "Historii upraw nie podano" in default
    assert "Podana Historia upraw to potwierdza" in confirmed
    assert "inną Uprawę w roku 2015; nie zmienia to Podatności wieloletniej" in other
    assert "Lata niepodane (2014, 2016, " in other
    assert "nie wskazuje innej Uprawy w żadnym roku" in same_named


def test_trace_entry_holds_both_counts():
    course, assessment = course_of(years(y2015="bare_field"))
    entry = history_texts.trace_entry(course, assessment.multiyear_susceptibility)
    assert entry.rule_id == "crop_history.course"
    assert entry.values["course_deficit_years"] == 9
    assert entry.values["course_assessed_years"] == 9
    assert entry.values["susceptibility_deficit_years"] == 10
    assert entry.result == "9 z 9 lat"


@pytest.mark.parametrize(
    "history", [SAME, years(y2015="bare_field", y2021=SPRING.id, y2023=SPRING.id)]
)
def test_texts_are_repeatable_and_keep_to_the_glossary(history):
    course, part = section(history)
    assert section(history)[1] == part
    texts = [part.comparison_sentence, history_texts.assumption(BASE, course)]
    texts += [year.satellite_note for year in part.years]
    for text in texts:
        assert not any(word in text.lower() for word in AVOIDED), text
        assert "Przebieg historyczny zastępuje" not in text
