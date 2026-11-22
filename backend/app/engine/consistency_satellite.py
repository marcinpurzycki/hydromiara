"""The satellite reading for the period of the analysis date, described.

No rule is given yet for reading a water deficit from the vegetation indices,
so the reading is shown next to the verdict and never changes the result of
the consistency check: this comparison always ends without a result. Outside
the crop season, and for the field without a crop, the reading describes only
the cover of the field.

Scenes taken after the analysis date are never read.
"""

from datetime import date, timedelta
from typing import Literal

from app.contracts.source_data import SatelliteData, SatelliteScene
from app.contracts.verdicts import ConsistencyItem
from app.engine.consistency_params import ConsistencyParams
from app.engine.consistency_parts import NO_DATA, NO_EFFECT, Comparison, period, pl

# Where the analysis date lies for the crop.
SeasonState = Literal["in_season", "out_of_season", "no_crop"]

SOURCE = "Copernicus Sentinel-2 (odczyt satelitarny)"

_MEANING = {
    "in_season": (
        "Odczyt opisowy: NDVI opisuje zieloność pokrywy pola, NDMI zawartość wody "
        "w roślinach."
    ),
    "out_of_season": (
        "Data analizy jest poza Sezonem uprawy: odczyt opisuje tylko pokrywę pola, "
        "nie niedobór wody."
    ),
    "no_crop": "Pole bez uprawy: odczyt opisuje tylko pokrywę pola, nie niedobór wody.",
}
_COVER_ONLY = {
    "in_season": "",
    "out_of_season": (
        " Data analizy jest poza Sezonem uprawy, więc opisuje on tylko pokrywę pola, "
        "nie niedobór wody."
    ),
    "no_crop": " Dla Pola bez uprawy opisuje on tylko pokrywę pola, nie niedobór wody.",
}
_EARLIER = "Wcześniejszy odczyt, podany do porównania."


def _number(value: float | None) -> str:
    return "brak" if value is None else f"{value:.2f}".replace(".", ",")


def _values(scene: SatelliteScene) -> str:
    return f"NDVI {_number(scene.ndvi)}; NDMI {_number(scene.ndmi)}"


def _usable(scene: SatelliteScene) -> bool:
    return scene.ndvi is not None or scene.ndmi is not None


def scene_values(scene: SatelliteScene) -> str:
    """Both indices of the scene as shown to the user."""
    return _values(scene)


def usable(scene: SatelliteScene) -> bool:
    """True when the scene has at least one of the two indices."""
    return _usable(scene)


def _item(scene: SatelliteScene, meaning: str) -> ConsistencyItem:
    return ConsistencyItem(
        source=SOURCE, period=pl(scene.date), value=_values(scene), meaning=f"{meaning} {NO_EFFECT}"
    )


def describe_satellite(
    satellite: SatelliteData | None,
    analysis_date: date,
    *,
    season_state: SeasonState,
    params: ConsistencyParams,
) -> Comparison:
    """Items for the newest scene of the period and for earlier scenes; no result."""
    first_day = analysis_date - timedelta(days=params.satellite_max_scene_age_days)
    span = period(first_day, analysis_date)
    if satellite is None:
        missing = ConsistencyItem(
            source=SOURCE,
            period=span,
            value=NO_DATA,
            meaning="Brak odczytów satelitarnych dla Działki.",
        )
        return Comparison(
            items=(missing,),
            result=None,
            clause="Odczytów satelitarnych dla Działki nie ma.",
            facts={"satellite_scene": None},
        )

    scenes = sorted(
        (scene for scene in satellite.scenes if scene.date <= analysis_date and _usable(scene)),
        key=lambda scene: scene.date,
        reverse=True,
    )
    current = next((scene for scene in scenes if scene.date >= first_day), None)
    earlier = [scene for scene in scenes if scene.date < first_day]
    if current is None:
        head = ConsistencyItem(
            source=SOURCE,
            period=span,
            value=NO_DATA,
            meaning="Brak odczytu satelitarnego z tego okresu.",
        )
        clause = f"Odczytu satelitarnego z okresu {span} nie ma."
    else:
        head = _item(current, _MEANING[season_state])
        clause = (
            f"Odczyt satelitarny z {pl(current.date)} ({_values(current)}) jest podany "
            f"opisowo i nie wpływa na wynik.{_COVER_ONLY[season_state]}"
        )
    return Comparison(
        items=(head, *(_item(scene, _EARLIER) for scene in earlier)),
        result=None,
        clause=clause,
        facts={"satellite_scene": None if current is None else current.date.isoformat()},
    )
