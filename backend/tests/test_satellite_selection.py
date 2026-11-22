"""One scene per day on one tile, and the order in which clear scenes are read."""

from datetime import date, timedelta

from app.sources import satellite_params as params
from app.sources.satellite_providers import EARTH_SEARCH, PLANETARY_COMPUTER
from app.sources.satellite_search import SceneItem, SearchWindow, parse_items, search_windows
from app.sources.satellite_selection import by_preference, main_tile, one_per_day
from tests.satellite_helpers import recorded_answer
from tests.test_satellite_chain import pc_answer

MONTH = SearchWindow(start=date(2023, 5, 21), end=date(2023, 6, 20), anchor=date(2023, 6, 20))


def item(day: date, tile: str = "34UCD", baseline: str = "05.09", suffix: str = "a") -> SceneItem:
    return SceneItem(f"S2_{tile}_{day:%Y%m%d}_{suffix}", day, {}, 0.0, tile, baseline)


def test_most_frequent_tile_is_used_and_a_tie_goes_to_the_first_by_name():
    day = date(2023, 6, 1)
    assert main_tile([item(day, "34UCD"), item(day, "33UYU"), item(day, "34UCD", suffix="b")]) == "34UCD"
    assert main_tile([item(day, "34UCD"), item(day, "33UYU")]) == "33UYU"
    assert main_tile([]) == ""


def test_one_scene_per_day_always_on_the_same_tile():
    days = [date(2023, 6, d) for d in (1, 4, 6)]
    items = [item(day, tile) for day in days for tile in ("34UCD", "33UYU")]
    kept = one_per_day(items, "34UCD")
    assert [scene.date for scene in kept] == sorted(days, reverse=True)
    assert {scene.tile for scene in kept} == {"34UCD"}
    assert one_per_day(list(reversed(items)), "34UCD") == kept


def test_highest_processing_version_wins_then_the_greater_identifier():
    day = date(2023, 6, 1)
    old, new = item(day, baseline="05.09", suffix="z"), item(day, baseline="05.10", suffix="a")
    assert one_per_day([old, new], "34UCD") == [new]
    assert one_per_day([new, old], "34UCD") == [new]
    first, second = item(day, suffix="a"), item(day, suffix="b")
    assert one_per_day([first, second], "34UCD") == [second]
    assert one_per_day([second, first], "34UCD") == [second]


def test_recorded_planetary_computer_answer_is_reduced_to_one_scene_per_day():
    items = parse_items(pc_answer(), MONTH, PLANETARY_COMPUTER)
    assert len(items) == 45  # two tiles, up to two processing versions a day
    tile = main_tile(items)
    kept = one_per_day(items, tile)
    assert tile == "34UCD"
    assert len(kept) == len({scene.date for scene in items}) == 12
    assert [scene.date for scene in kept] == sorted((s.date for s in kept), reverse=True)
    for scene in kept:
        copies = [other for other in items if other.date == scene.date and other.tile == tile]
        assert scene.baseline == max(other.baseline for other in copies)


def test_recorded_earth_search_answer_is_reduced_to_one_scene_per_day():
    items = parse_items(recorded_answer(), MONTH, EARTH_SEARCH)
    assert len(items) == 24
    assert main_tile(items) == "MGRS-33UYU"
    assert len(one_per_day(items, "MGRS-33UYU")) == 12


def test_current_window_prefers_the_newest_scenes():
    days = [date(2023, 6, d) for d in (3, 19, 11)]
    ordered = by_preference(MONTH, [item(day) for day in days])
    assert [scene.date for scene in ordered] == [date(2023, 6, d) for d in (19, 11, 3)]


def test_window_of_an_earlier_year_prefers_days_nearest_to_the_same_day_of_the_year():
    window = search_windows(date(2023, 6, 20))[1]
    assert window.anchor == date(2022, 6, 20) and not window.current
    days = [window.anchor + timedelta(days=offset) for offset in (-9, 2, -2, 14, 0)]
    ordered = by_preference(window, [item(day) for day in days])
    offsets = [(scene.date - window.anchor).days for scene in ordered]
    assert offsets == [0, 2, -2, -9, 14]  # equally near: the later day first


def test_bands_are_read_for_at_most_sixteen_scenes():
    windows = search_windows(date(2023, 6, 20))
    assert [window.quota for window in windows] == [6, 2, 2, 2, 2, 2]
    assert sum(window.quota for window in windows) == params.MAX_SCENES == 16
