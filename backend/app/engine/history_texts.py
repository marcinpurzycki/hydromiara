"""Wording of the historical course and of the crop history assumption.

Everything here only describes: the comparison sentence puts the numbers of
the historical course next to those of the multi-year susceptibility and says
that the first does not replace the second; the satellite note of a year
gives the date and the values of a scene and what the crop of that year means
for reading it, without judging anything.
"""

from app.catalog.crop_model import CatalogCrop
from app.contracts.report import TraceEntry
from app.contracts.verdicts import CropRef, HistoricalCourse, HistoricalYear
from app.engine.consistency_parts import pl
from app.engine.consistency_satellite import scene_values
from app.engine.history import CourseResult, CourseYear
from app.engine.susceptibility import SusceptibilityVerdict

NO_SCENE = "Brak odczytu satelitarnego z tego roku."
NOT_REPLACING = (
    "Przebieg historyczny stoi obok Podatności wieloletniej i jej nie zastępuje: Stopień "
    "niedoboru, Przyczyny niedoboru i Rekomendacje wynikają z Podatności wieloletniej "
    "i z Bieżącej sytuacji wodnej."
)

_NOT_ASSESSED = {
    "no_crop": "dla Pola bez uprawy Stopień niedoboru nie jest wyznaczany",
    "no_weather": "brak danych pogodowych z Okresu krytycznego",
    "not_started": "Okres krytyczny tej Uprawy zaczyna się po Dacie analizy",
}
_NOT_ASSESSED_SHORT = {
    "no_crop": "Pole bez uprawy",
    "no_weather": "brak danych pogodowych",
    "not_started": "Okres krytyczny po Dacie analizy",
}


def _of_years(count: int, *, assessed: bool = False) -> str:
    """"z 10 lat", "z 1 roku", "z 8 ocenionych lat"."""
    if count == 1:
        return "z 1 ocenionego roku" if assessed else "z 1 roku"
    return f"z {count} ocenionych lat" if assessed else f"z {count} lat"


def _listed(years: list[int] | tuple[int, ...]) -> str:
    return ", ".join(str(year) for year in years)


def _in_years(years: list[int] | tuple[int, ...]) -> str:
    return f"{'roku' if len(years) == 1 else 'latach'} {_listed(years)}"


def assumption(base: str, course: CourseResult | None) -> str:
    """The sentence about the crop history assumption of the susceptibility.

    `base` says how the susceptibility is computed; what follows says whether
    a history was given and that it does not change the susceptibility.
    """
    if course is None:
        return (
            f"{base} Historii upraw nie podano, więc przyjęto, że ta Uprawa rosła tu "
            "w każdym roku."
        )
    if course.same_every_year:
        return f"{base} Podana Historia upraw to potwierdza: ta Uprawa rosła tu w każdym roku."
    missing = [year.year for year in course.years if not year.given]
    rest = (
        f" Lata niepodane ({_listed(missing)}) przyjmują Uprawę z sezonu Daty analizy."
        if missing
        else ""
    )
    other = course.other_crop_years
    if not other:
        return f"{base} Podana Historia upraw nie wskazuje innej Uprawy w żadnym roku.{rest}"
    return (
        f"{base} Podana Historia upraw wskazuje inną Uprawę w {_in_years(other)}; nie "
        "zmienia to Podatności wieloletniej, a to, co faktycznie rosło, pokazuje Przebieg "
        f"historyczny.{rest}"
    )


def satellite_note(year: CourseYear, course: CourseResult) -> str:
    """Per-year note: why the year is not assessed (if so) and its satellite reading."""
    parts = []
    if year.not_assessed is not None:
        parts.append(f"Roku nie oceniono: {_NOT_ASSESSED[year.not_assessed]}.")
    elif year.partial:
        parts.append(f"Rok oceniony tylko do Daty analizy ({pl(course.analysis_date)}).")
    if year.scene is None:
        parts.append(NO_SCENE)
        return " ".join(parts)
    reading = f"Odczyt satelitarny z {pl(year.scene.date)}: {scene_values(year.scene)}."
    origin = "według Historii upraw" if year.given or course.same_every_year else (
        "przyjęta z sezonu Daty analizy"
    )
    if year.crop.is_bare_field:
        meaning = (
            f"Według Historii upraw było to {year.crop.name}, więc odczyt opisuje tylko "
            "pokrywę pola, nie niedobór wody."
        )
    elif year.scene_in_season:
        meaning = (
            f"Uprawa {origin}: {year.crop.name}; dzień odczytu wypada w jej Sezonie uprawy. "
            "Odczyt jest opisowy i nie wpływa na ocenę roku."
        )
    else:
        meaning = (
            f"Uprawa {origin}: {year.crop.name}; dzień odczytu wypada poza jej Sezonem "
            "uprawy, więc odczyt opisuje tylko pokrywę pola, nie niedobór wody."
        )
    parts.extend((reading, meaning))
    return " ".join(parts)


def comparison_sentence(
    course: CourseResult, verdict: SusceptibilityVerdict, crop: CatalogCrop
) -> str:
    """Numbers of both views side by side, where they differ, and what was left out."""
    assessed = course.assessed_years
    if assessed:
        first = (
            "Według Historii upraw temu, co faktycznie rosło na Działce, wody brakowało "
            f"w {course.deficit_years} {_of_years(assessed, assessed=assessed < len(course.years))}."
        )
    else:
        first = "Według Historii upraw nie dało się ocenić żadnego roku Okna wieloletniego."
    if verdict.assessed:
        second = (
            f"Bieżącej Uprawie ({crop.name}), gdyby rosła tu w każdym roku, brakowałoby "
            f"w {verdict.deficit_years} {_of_years(verdict.total_years)} — to Podatność "
            "wieloletnia."
        )
    else:
        second = "Podatności wieloletniej nie oceniono."
    parts = [first, second]

    of_analysis = {year.year: year.deficit for year in verdict.years if year.assessed}
    both = [year for year in course.years if year.assessed and year.year in of_analysis]
    differing = [year.year for year in both if year.deficit != of_analysis[year.year]]
    if differing:
        parts.append(f"Oba ujęcia różnią się w {_in_years(differing)}.")
    elif both and len(both) == len(of_analysis) == assessed:
        parts.append("W każdym roku oba ujęcia dają ten sam wynik.")

    left_out = [year for year in course.years if not year.assessed]
    if left_out:
        named = ", ".join(
            f"{year.year} ({_NOT_ASSESSED_SHORT[year.not_assessed]})" for year in left_out
        )
        parts.append(f"W Przebiegu historycznym nie oceniono: {named}.")
    parts.append(NOT_REPLACING)
    return " ".join(parts)


def course_section(
    course: CourseResult, verdict: SusceptibilityVerdict, crop: CatalogCrop
) -> HistoricalCourse:
    """The historical course in the shape of the Report.

    The Report has no "not assessed" state for a year: such a year is written
    with `deficit: false` and its note begins with why it was not assessed.
    """
    return HistoricalCourse(
        years=[
            HistoricalYear(
                year=year.year,
                crop=CropRef(id=year.crop.id, name=year.crop.name),
                deficit=year.deficit,
                satellite_note=satellite_note(year, course),
            )
            for year in course.years
        ],
        comparison_sentence=comparison_sentence(course, verdict, crop),
    )


def trace_entry(course: CourseResult, verdict: SusceptibilityVerdict) -> TraceEntry:
    """What the history was and that the verdicts did not read it."""
    return TraceEntry(
        rule_id="crop_history.course",
        condition=(
            "Przebieg historyczny: rok z niedoborem liczony tą samą miarą co w Podatności "
            "wieloletniej, dla Uprawy z Historii upraw; nie wpływa na werdykty, Pewność "
            "oceny, Przyczyny niedoboru ani Rekomendacje"
        ),
        values={
            "same_every_year": course.same_every_year,
            "years_given": sum(year.given for year in course.years),
            "years_with_other_crop": len(course.other_crop_years),
            "course_deficit_years": course.deficit_years,
            "course_assessed_years": course.assessed_years,
            "susceptibility_deficit_years": verdict.deficit_years,
            "susceptibility_total_years": verdict.total_years,
        },
        result=f"{course.deficit_years} {_of_years(course.assessed_years)}",
    )
