"""Checks of a crop history sent by the user, shared by the routes that take one.

A history is checked against the analysis it belongs to: the crop and the
analysis date set the years of the multi-year window, and only those years
can be named. Nothing is dropped silently: a year outside the window or a
crop without parameters in the catalogue is refused with a message that says
what can be sent instead.
"""

from datetime import date

from app.api.errors import ApiError
from app.catalog.crops import get_crop, has_crop
from app.contracts.analyses import CropHistory
from app.engine.history import window_years, years_outside_window


def require_valid_history(history: CropHistory, crop_id: str, analysis_date: date) -> None:
    """Raise unless the history can be used for an analysis of the crop on the date."""
    crop = get_crop(crop_id)
    if crop.is_bare_field:
        raise ApiError(
            409,
            "crop_history_not_applicable",
            "Ten raport dotyczy Pola bez uprawy: nie ma Uprawy, o której Historię upraw "
            "można zapytać, więc Historii upraw się dla niego nie podaje.",
        )
    unknown = sorted(
        f"{year}: {named}" for year, named in (history.years or {}).items() if not has_crop(named)
    )
    if unknown:
        raise ApiError(
            422,
            "unknown_crop",
            f"Historia upraw zawiera nieznaną Uprawę ({'; '.join(unknown)}). "
            "Wybierz Uprawy z listy.",
        )
    outside = years_outside_window(history, crop, analysis_date)
    if outside:
        window = window_years(crop, analysis_date)
        raise ApiError(
            422,
            "crop_history_year_outside_window",
            f"Historia upraw może dotyczyć tylko lat Okna wieloletniego tej analizy "
            f"({window[0]}–{window[-1]}). Poza nim: {', '.join(str(year) for year in outside)}.",
        )


def carried_history(
    history: CropHistory | None, crop_id: str, analysis_date: date
) -> CropHistory | None:
    """The history of a Report for a new analysis of the same crop on another date.

    A history speaks about years, not about the analysis date, so it goes
    with the new analysis; years that fall out of the new window are left out.
    """
    if history is None or history.years is None:
        return history
    window = set(window_years(get_crop(crop_id), analysis_date))
    return CropHistory(years={year: named for year, named in history.years.items() if year in window})
