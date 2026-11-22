"""Wording of the satellite reading in the consistency check."""

from app.contracts.source_data import SatelliteScene
from app.engine.satellite_crops import CropReading
from app.engine.satellite_reading import DEFAULT_READING_PARAMS, Change, Reading

SOURCE = "Copernicus Sentinel-2 (odczyt satelitarny)"

_IN_SEASON = (
    "Odczyt opisowy: NDVI opisuje zieloność pokrywy pola, NDMI zawartość wody w roślinach."
)
_MEANING = {
    "in_season": _IN_SEASON,
    "out_of_season": (
        "Data analizy jest poza Sezonem uprawy: odczyt opisuje tylko pokrywę pola, "
        "nie niedobór wody."
    ),
    "no_crop": "Pole bez uprawy: odczyt opisuje tylko pokrywę pola, nie niedobór wody.",
}
_OUTSIDE_CRITICAL = (
    "Kierunek zmiany i porównanie z wcześniejszymi latami podajemy tylko w Okresie krytycznym."
)
COVER_ONLY = {
    "in_season": "",
    "out_of_season": (
        " Data analizy jest poza Sezonem uprawy, więc opisuje on tylko pokrywę pola, "
        "nie niedobór wody."
    ),
    "no_crop": " Dla Pola bez uprawy opisuje on tylko pokrywę pola, nie niedobór wody.",
}

# Limitation: decision of the project that outside the season the reading
# only describes the cover and lowers the confidence of the current status.
OUT_OF_SEASON = (
    "Data analizy jest poza Sezonem uprawy: zdjęcia satelitarne opisują tylko, czy pole jest "
    "pokryte roślinami, i nie potwierdzają Bieżącej sytuacji wodnej."
)

# What the reading says next to the balance, by `Reading.signal`.
SIGNAL = {
    "confirms": "Bilans wodny wskazuje niedobór, a odczyt satelitarny go potwierdza.",
    "does_not_confirm": (
        "Bilans wodny wskazuje niedobór, którego odczyt satelitarny jeszcze nie potwierdza: "
        "rośliny reagują na brak wody z opóźnieniem od kilku dni do kilku tygodni, więc nie "
        "jest to rozbieżność."
    ),
    "contradicts": (
        "Bilans wodny nie wskazuje niedoboru, a NDMI istotnie spada w Okresie krytycznym."
    ),
    "no_objection": (
        "Bilans wodny nie wskazuje niedoboru i odczyt satelitarny nie pokazuje istotnego spadku."
    ),
}

_NO_HISTORY = (
    "Nie wiemy, co rosło na Działce w poprzednich latach, więc nie porównujemy dzisiejszych "
    "zdjęć z dawnymi. Podaj Historię upraw, żeby zobaczyć takie porównanie."
)
_INDEX_NAMES = {"ndvi": "NDVI", "ndmi": "NDMI"}


def number(value: float | None) -> str:
    return "brak" if value is None else f"{value:.2f}".replace(".", ",")


def _signed(value: float) -> str:
    return f"{value:+.2f}".replace(".", ",").replace("-", "−")


def values(scene: SatelliteScene) -> str:
    return f"NDVI {number(scene.ndvi)}; NDMI {number(scene.ndmi)}"


def crop_mismatch(april_ndvi: float | None) -> str:
    limit = number(DEFAULT_READING_PARAMS.april_min_ndvi)
    return (
        "Zdjęcia satelitarne z kwietnia nie pasują do Uprawy ozimej: Działka była wtedy prawie "
        f"bez roślin (mediana NDVI {number(april_ndvi)}, poniżej {limit}). Sprawdź, czy "
        "wybrana Uprawa jest właściwa; oba werdykty policzono dla tej Uprawy."
    )


def cover_meaning(season_state: str, reading: Reading, rules: CropReading) -> str:
    """What the newest scene describes, by the place of the date in the season."""
    meaning = _MEANING[season_state]
    if season_state != "in_season":
        return meaning
    if not reading.interpreted:
        return f"{meaning} {_OUTSIDE_CRITICAL}"
    note = f" {rules.note}" if rules.note else ""
    return f"{meaning} Nie stosujemy progów bezwzględnych.{note}"


def _change_text(change: Change) -> str:
    name = _INDEX_NAMES[change.index]
    size = number(abs(change.difference))
    if change.direction == "falls":
        return f"{name} spada o {size}"
    if change.direction == "rises":
        return f"{name} rośnie o {size}"
    return f"{name} bez zmian ({_signed(change.difference)})"


def change_value(reading: Reading) -> str:
    if not reading.changes:
        return "brak danych"
    return "; ".join(_change_text(change) for change in reading.changes)


def change_meaning(reading: Reading) -> str:
    limit = number(DEFAULT_READING_PARAMS.significant_change)
    if not reading.changes:
        return (
            "Kierunek zmiany wymaga co najmniej dwóch odczytów z tego okresu: jeden odczyt "
            "nie wystarcza do wniosku."
        )
    count = max(change.earlier_scenes for change in reading.changes)
    return (
        "Kierunek zmiany w Okresie krytycznym: najnowszy odczyt wobec mediany wcześniejszych "
        f"odczytów z tego okresu (jest ich {count}); zmianę liczymy od {limit}."
    )


def years_period(reading: Reading) -> str:
    years = reading.years
    if years is None or not years.years:
        return "wcześniejsze lata"
    return "lata " + ", ".join(str(year) for year in years.years)


def years_value(reading: Reading) -> str:
    years = reading.years
    if years is None:
        return "nie porównano"
    if years.difference is None:
        return "brak danych"
    size = number(abs(years.difference))
    if years.direction == "falls":
        return f"NDMI niższy o {size} niż w latach tej samej Uprawy"
    if years.direction == "rises":
        return f"NDMI wyższy o {size} niż w latach tej samej Uprawy"
    return f"NDMI zbliżony do lat tej samej Uprawy ({_signed(years.difference)})"


def years_meaning_for(reading: Reading) -> str:
    years = reading.years
    needed = DEFAULT_READING_PARAMS.min_same_crop_years
    days = DEFAULT_READING_PARAMS.history_half_window_days
    if years is None:
        return _NO_HISTORY
    if years.difference is None:
        return (
            f"Porównanie z wcześniejszymi latami wymaga co najmniej {needed} lat, w których "
            "Historia upraw podaje tę samą Uprawę i jest odczyt z tego samego okresu roku; "
            f"takich lat jest {len(years.years)}."
        )
    return (
        "Porównanie NDMI najnowszego odczytu z medianą z lat, w których według Historii upraw "
        f"rosła ta sama Uprawa (odczyty z {days} dni przed i po tym samym dniu roku)."
    )
