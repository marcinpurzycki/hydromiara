"""Report limitations for search windows that ended without a satellite reading.

At most one limitation concerns the current window and at most one all the
windows of earlier years together, so that a reading with gaps never weighs
more in the confidence of a verdict than no reading at all.
"""

from dataclasses import dataclass, field
from datetime import date as Date
from typing import Literal

from app.contracts.report import Limitation
from app.contracts.source_data import SatelliteScene
from app.sources import satellite_params as params
from app.sources.satellite_search import SearchWindow

WindowStatus = Literal[
    "unfinished",  # the time budget ran out before the window was done
    "found",
    "no_scenes",  # the catalogue has nothing for the window
    "no_clear",  # no scene with enough clear pixels over the parcel
    "too_small",  # too few pixels fit inside the parcel outline
    "search_failed",
    "before_archive",  # the window ends before the first scene of the service
]


@dataclass
class WindowState:
    """Progress of one search window; filled in while the window is worked on."""

    window: SearchWindow
    status: WindowStatus = "unfinished"
    scenes: list[SatelliteScene] = field(default_factory=list)
    # True when the parcel has too few 20 m pixels for the water content index.
    ndmi_missing: bool = False


TOO_SMALL_TEXT = (
    "Działka jest za mała lub za wąska, żeby wiarygodnie odczytać ją ze zdjęć satelitarnych "
    "(piksel ma 10–20 m). Ocena opiera się na bilansie wodnym."
)
NARROW_TEXT = (
    "Działka jest wąska: ze zdjęć satelitarnych odczytujemy tylko zieloność roślin (NDVI), "
    "bez wskaźnika zawartości wody w roślinach (NDMI)."
)
_NO_CONFIRMATION = "Ocena opiera się na bilansie wodnym, bez potwierdzenia ze zdjęć."

# Why a window of an earlier year has no reading, as listed in the Report.
_YEAR_REASONS: dict[WindowStatus, str] = {
    "no_scenes": "brak zdjęć w katalogu",
    "no_clear": "brak zdjęcia bez chmur",
    "search_failed": "katalog zdjęć nie odpowiedział",
    "unfinished": "odczyt nie zmieścił się w limicie czasu",
    "before_archive": "przed początkiem archiwum zdjęć",
}


def _pl(day: Date) -> str:
    return day.strftime("%d.%m.%Y")


def _current_text(state: WindowState, time_budget_s: float, archive_note: str) -> str:
    period = f"{_pl(state.window.start)}–{_pl(state.window.end)}"
    days = params.CURRENT_WINDOW_DAYS
    if state.status == "no_scenes":
        return (
            f"Katalog nie zawiera zdjęć satelitarnych Działki z {days} dni przed Datą analizy "
            f"({period}). {_NO_CONFIRMATION}"
        )
    if state.status == "no_clear":
        return (
            f"W {days} dniach przed Datą analizy ({period}) nie było zdjęcia satelitarnego "
            f"bez chmur nad Działką (co najmniej {params.MIN_CLEAR_SHARE_PCT:g}% czystych "
            f"pikseli). {_NO_CONFIRMATION}"
        )
    if state.status == "search_failed":
        return (
            f"Katalog zdjęć satelitarnych nie odpowiedział na zapytanie o okres {period}. "
            f"{_NO_CONFIRMATION}"
        )
    if state.status == "before_archive":
        return f"{archive_note} Dla okresu {period} nie ma potwierdzenia ze zdjęć."
    return (
        f"Odczyt zdjęć satelitarnych z okresu {period} nie zmieścił się w limicie czasu "
        f"({time_budget_s:g} s). {_NO_CONFIRMATION}"
    )


def _history_text(missing: list[WindowState], archive_note: str) -> str:
    """One sentence for all earlier years without a reading, grouped by the reason."""
    by_reason: dict[str, list[int]] = {}
    for state in missing:
        by_reason.setdefault(_YEAR_REASONS[state.status], []).append(state.window.anchor.year)
    groups = "; ".join(
        f"{', '.join(str(year) for year in sorted(years))} ({reason})"
        for reason, years in by_reason.items()
    )
    text = (
        "Z tego samego okresu roku nie ma odczytu satelitarnego dla lat: "
        f"{groups}. Dla tych lat nie ma potwierdzenia ze zdjęć."
    )
    if any(state.status == "before_archive" for state in missing):
        text = f"{text} {archive_note}"
    return text


def gave_no_result(states: list[WindowState]) -> bool:
    """True when a service delivered no reading and did not finish its work.

    This is the case for asking the next service. A service that answered
    for every window, even with nothing usable, has given its result.
    """
    delivered = any(state.scenes for state in states)
    stuck = any(state.status in ("unfinished", "search_failed") for state in states)
    return stuck and not delivered


def find_limitations(
    states: list[WindowState], time_budget_s: float, archive_note: str = ""
) -> list[Limitation]:
    """What the reading lacks: the current window first, then the earlier years.

    The first window ends on the analysis date and concerns the current
    status; the others are the same period of earlier years. A parcel too
    small for either index gives a single limitation for all windows.
    """
    if any(state.status == "too_small" for state in states):
        return [Limitation(text=TOO_SMALL_TEXT, affects="all", permanent=False)]
    found = []
    current, earlier = states[0], states[1:]
    if current.status != "found" and current.scenes:
        text = (
            f"Odczyt zdjęć satelitarnych z {params.CURRENT_WINDOW_DAYS} dni przed Datą analizy "
            f"przerwał limit czasu ({time_budget_s:g} s); wykorzystano zdjęcia odczytane "
            "do tej chwili."
        )
        found.append(Limitation(text=text, affects="current", permanent=False))
    elif current.status != "found":
        text = _current_text(current, time_budget_s, archive_note)
        found.append(Limitation(text=text, affects="current", permanent=False))
    elif current.ndmi_missing:
        found.append(Limitation(text=NARROW_TEXT, affects="current", permanent=False))
    # A year cut short by the time limit counts with the scenes it has.
    missing = [state for state in earlier if state.status != "found" and not state.scenes]
    if missing:
        text = _history_text(missing, archive_note)
        found.append(Limitation(text=text, affects="multiyear", permanent=False))
    return found
