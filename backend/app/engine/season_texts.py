"""Report wording for the season: the season section, irrigation, headline, trace.

The wording of the current water status outside the season and in dormancy is
in `season_store`. Pure: every function returns the same text for the same input.
"""

from datetime import date

from app.catalog.crop_model import CatalogCrop
from app.contracts.causes import Irrigation
from app.contracts.report import TraceEntry
from app.contracts.verdicts import DateRange, Season
from app.engine.consistency_parts import period, pl
from app.engine.season import DateState, SeasonStatus
from app.engine.verdicts import CurrentVerdict

RULE_ID = "season.state"

# Shown word for word whenever the analysis date is outside the crop season.
OFF_SEASON_IRRIGATION = "Rekomendacje nawadniania: brak — wybrana data jest poza sezonem"

STORE_LABEL_PREFIX = "Zapas wody w glebie"
STORE_NOT_NEEDS = "Stopień niedoboru dotyczy Zapasu wody w glebie, nie potrzeb rośliny"
_NO_CROP_NOTE = "Pole bez uprawy nie ma Sezonu uprawy."
_STATE_NAMES: dict[DateState, str] = {
    "in_season": "w Sezonie uprawy",
    "dormant": "w Sezonie uprawy, w spoczynku",
    "out_of_season": "poza Sezonem uprawy",
    "no_crop": "Pole bez uprawy",
}


def span(dates) -> str:
    return period(dates.start, dates.end)


def days(count: int) -> str:
    return f"{count} dzień" if count == 1 else f"{count} dni"


def store_label(level_label: str) -> str:
    """Deficit level signed as a level of the soil water store."""
    return f"{STORE_LABEL_PREFIX}: {level_label}"


def season_note(crop: CatalogCrop, status: SeasonStatus, analysis_date: date) -> str | None:
    if status.state == "no_crop":
        return _NO_CROP_NOTE
    if status.state == "out_of_season":
        return (
            f"Data analizy {pl(analysis_date)} jest poza Sezonem uprawy {crop.name_genitive}. "
            f"Ostatni Sezon uprawy: {span(status.last_season)}. Bieżąca sytuacja wodna "
            "opisuje miniony sezon i odbudowę Zapasu wody w glebie, a jej "
            f"{STORE_NOT_NEEDS}. {OFF_SEASON_IRRIGATION}."
        )
    if status.state == "dormant":
        return (
            f"Data analizy {pl(analysis_date)} wypada w Sezonie uprawy {crop.name_genitive} "
            f"({span(status.last_season)}), ale uprawa jest w spoczynku "
            f"({span(status.dormancy)}). Oceniany jest Zapas wody w glebie: "
            f"{STORE_NOT_NEEDS}."
        )
    return None


def season_section(crop: CatalogCrop, status: SeasonStatus, analysis_date: date) -> Season:
    latest = status.last_season
    return Season(
        in_season=status.in_season,
        last_season=None if latest is None else DateRange(start=latest.start, end=latest.end),
        note=season_note(crop, status, analysis_date),
    )


def off_season_irrigation(crop: CatalogCrop, status: SeasonStatus) -> Irrigation | None:
    """The irrigation part outside the season; None in every other state."""
    if status.state != "out_of_season":
        return None
    text = (
        f"{OFF_SEASON_IRRIGATION}. Ostatni Sezon uprawy {crop.name_genitive}: "
        f"{span(status.last_season)}."
    )
    return Irrigation(
        applicable=False,
        text=text,
        justified=None,
        amount_mm=None,
        amount_m3_ha=None,
        timing=None,
        reason_if_none=text,
    )


def headline_sentence(
    status: SeasonStatus, analysis_date: date, verdict: CurrentVerdict
) -> str | None:
    """First sentence of the headline when the store is assessed; None otherwise."""
    if not (status.store_assessed and verdict.assessed):
        return None
    if status.state == "dormant":
        opening = f"W dniu {pl(analysis_date)} uprawa jest w spoczynku"
    else:
        opening = f"Data analizy {pl(analysis_date)} jest poza Sezonem uprawy"
    return f"{opening} — {store_label(verdict.label)}."


def trace_entry(status: SeasonStatus, critical_date: date | None) -> TraceEntry:
    def iso(dates, end: bool = False) -> str | None:
        return None if dates is None else (dates.end if end else dates.start).isoformat()

    return TraceEntry(
        rule_id=RULE_ID,
        condition=(
            "w Sezonie uprawy: Data analizy od siewu do zbioru; w spoczynku: uprawa ozima od "
            "końca jesiennych wschodów do dnia przed wiosennym wzrostem; poza Sezonem uprawy "
            "i w spoczynku Stopień niedoboru dotyczy Zapasu wody w glebie; analiza Okresu "
            "krytycznego: środek ostatniego Okresu krytycznego, którego środek nie jest "
            "późniejszy niż Data analizy"
        ),
        values={
            "season_state": status.state,
            "last_season_start": iso(status.last_season),
            "last_season_end": iso(status.last_season, end=True),
            "dormancy_start": iso(status.dormancy),
            "dormancy_end": iso(status.dormancy, end=True),
            "critical_period_analysis_date": (
                None if critical_date is None else critical_date.isoformat()
            ),
        },
        result=_STATE_NAMES[status.state],
    )
