"""Working rules of the consistency check, kept apart from the code.

No source gives the rules for setting the verdict of the Report against the
drought indicator or against the satellite readings, so every rule here is the
simplest explicit one. Replacing a rule is a change of this file only.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

# What a class of the drought indicator says in the comparison.
CdiSignal = Literal["drought", "no_drought", "transitional"]

# PROVISIONAL: no source; lowest deficit level (0-3) of the current water
# status that counts as "the Report finds a water deficit" in the comparison.
DEFICIT_FROM_LEVEL: int = 1

# PROVISIONAL: no source for how the indicator classes map onto the verdict.
# Simplest reading of the class names: watch, warning and alert (1-3) signal
# a drought, class 0 signals none, and the recovery classes (4-6) are left
# out of the comparison because their names settle neither.
CDI_CLASS_SIGNALS: Mapping[int, CdiSignal] = {
    0: "no_drought",
    1: "drought",
    2: "drought",
    3: "drought",
    4: "transitional",
    5: "transitional",
    6: "transitional",
}

# PROVISIONAL: no source; whether the indicator is compared with the current
# water status when the analysis date lies outside the crop season (the
# deficit level then describes the soil water store, not the crop demand).
CDI_COMPARED_OUT_OF_SEASON: bool = True

# PROVISIONAL: no source; a scene taken at most this many days before the
# analysis date is described as the reading for the same period. Equal to the
# search window of the satellite adapter.
SATELLITE_MAX_SCENE_AGE_DAYS: int = 30

# First ten-day period of the indicator files the application is shipped with
# (see the data source table of the project README); not a tuned value.
CDI_SERIES_START: date = date(2016, 1, 1)


@dataclass(frozen=True)
class ConsistencyParams:
    """The rules above as one immutable object; defaults are the module values."""

    deficit_from_level: int = DEFICIT_FROM_LEVEL
    cdi_class_signals: Mapping[int, CdiSignal] = field(
        default_factory=lambda: dict(CDI_CLASS_SIGNALS)
    )
    cdi_compared_out_of_season: bool = CDI_COMPARED_OUT_OF_SEASON
    satellite_max_scene_age_days: int = SATELLITE_MAX_SCENE_AGE_DAYS
    cdi_series_start: date = CDI_SERIES_START

    def __post_init__(self) -> None:
        if not 1 <= self.deficit_from_level <= 3:
            raise ValueError("the deficit threshold is a deficit level from 1 to 3")
        if self.satellite_max_scene_age_days < 0:
            raise ValueError("the scene age limit cannot be negative")


DEFAULT_CONSISTENCY_PARAMS = ConsistencyParams()
