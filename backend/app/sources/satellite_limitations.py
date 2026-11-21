"""Report limitations for search windows that ended without a satellite reading."""

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
    "too_small",  # no pixel centre fits inside the parcel outline
    "search_failed",
]


@dataclass
class WindowState:
    """Progress of one search window; filled in while the window is worked on."""

    window: SearchWindow
    status: WindowStatus = "unfinished"
    scenes: list[SatelliteScene] = field(default_factory=list)


TOO_SMALL_TEXT = (
    "Działka jest zbyt mała lub zbyt wąska na odczyt satelitarny: po odsunięciu od granicy "
    "nie mieści się w niej środek żadnego piksela obrazu."
)


def _pl(day: Date) -> str:
    return day.strftime("%d.%m.%Y")


def _window_text(state: WindowState, time_budget_s: float) -> str:
    period = f"{_pl(state.window.start)}–{_pl(state.window.end)}"
    if state.status == "no_scenes":
        return f"Katalog nie zawiera scen satelitarnych nad Działką z okresu {period}."
    if state.status == "no_clear":
        return (
            f"W okresie {period} żadna scena satelitarna nie ma nad Działką co najmniej "
            f"{params.MIN_CLEAR_SHARE_PCT:g}% czystych pikseli."
        )
    if state.status == "search_failed":
        return f"Katalog scen satelitarnych nie odpowiedział na zapytanie o okres {period}."
    return (
        f"Odczyt scen satelitarnych z okresu {period} nie zmieścił się w limicie czasu "
        f"({time_budget_s:g} s)."
    )


def find_limitations(states: list[WindowState], time_budget_s: float) -> list[Limitation]:
    """One limitation per window without a reading, in the order of the windows.

    The first window ends on the analysis date and concerns the current
    status; the others are the same period of earlier years. A parcel too
    small for any pixel gives a single limitation for all windows.
    """
    if any(state.status == "too_small" for state in states):
        return [Limitation(text=TOO_SMALL_TEXT, affects="all", permanent=False)]
    return [
        Limitation(
            text=_window_text(state, time_budget_s),
            affects="current" if position == 0 else "multiyear",
            permanent=False,
        )
        for position, state in enumerate(states)
        if state.status != "found"
    ]
