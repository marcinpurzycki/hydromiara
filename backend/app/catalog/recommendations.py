"""The closed recommendation catalogue: interface for the rule engine.

The data live in `recommendation_data`, the model in `recommendation_model`.
The catalogue is checked as a whole when this module is loaded, so a broken
entry stops the application at start instead of surfacing in a Report.
"""

from collections.abc import Sequence

from app.catalog.recommendation_data import CATALOG
from app.catalog.recommendation_model import CatalogRecommendation, entries_read


def check_catalog(entries: Sequence[CatalogRecommendation]) -> tuple[CatalogRecommendation, ...]:
    """The entries as a catalogue; raises when they do not form a consistent one.

    Identifiers are unique, and an entry may depend only on entries listed
    before it, so one pass in catalogue order decides every rule.
    """
    seen: set[str] = set()
    for entry in entries:
        if entry.id in seen:
            raise ValueError(f"recommendation {entry.id!r} is listed twice")
        for condition in entry.all_conditions():
            for other in entries_read(condition):
                if other not in seen:
                    raise ValueError(
                        f"recommendation {entry.id!r} depends on {other!r}, "
                        "which is not listed before it"
                    )
        seen.add(entry.id)
    return tuple(entries)


_CATALOG = check_catalog(CATALOG)
_BY_ID = {entry.id: entry for entry in _CATALOG}


def list_recommendations() -> tuple[CatalogRecommendation, ...]:
    """Every catalogue entry, in catalogue order."""
    return _CATALOG


def get_recommendation(recommendation_id: str) -> CatalogRecommendation:
    try:
        return _BY_ID[recommendation_id]
    except KeyError:
        raise KeyError(f"unknown recommendation: {recommendation_id!r}") from None
