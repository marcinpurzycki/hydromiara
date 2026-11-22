"""Choosing which catalogued scenes are read. Pure functions, fixed order.

A parcel in the overlap of two tiles is listed twice a day, and a day may
have several reprocessed copies. One scene per acquisition day is kept:
always on the same tile, so that the pixel grid over the parcel never
changes, and in the newest processing version.
"""

from collections import Counter
from collections.abc import Iterable

from app.sources.satellite_search import SceneItem, SearchWindow


def main_tile(items: Iterable[SceneItem]) -> str:
    """The tile most frequent among the scenes; of equally frequent ones the first by name."""
    counts = Counter(item.tile for item in items)
    if not counts:
        return ""
    most = max(counts.values())
    return min(tile for tile, count in counts.items() if count == most)


def one_per_day(items: Iterable[SceneItem], tile: str) -> list[SceneItem]:
    """One scene per acquisition day on `tile`, newest day first.

    Among the copies of a day the highest processing version wins, then the
    greater scene identifier.
    """
    best: dict = {}
    for item in items:
        if item.tile != tile:
            continue
        kept = best.get(item.date)
        if kept is None or (item.baseline, item.scene_id) > (kept.baseline, kept.scene_id):
            best[item.date] = item
    return [best[day] for day in sorted(best, reverse=True)]


def by_preference(window: SearchWindow, items: Iterable[SceneItem]) -> list[SceneItem]:
    """Scenes of a window in the order their bands are read.

    Current window: newest first. Window of an earlier year: nearest to the
    same day of the year first, the later of two equally near days first.
    """
    if window.current:
        return sorted(items, key=lambda item: item.date, reverse=True)
    return sorted(
        items,
        key=lambda item: (abs((item.date - window.anchor).days), -item.date.toordinal()),
    )
