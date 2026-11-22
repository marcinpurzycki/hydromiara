"""The satellite reading for the period of the analysis date, described.

The numbers come from `satellite_reading`; this module words them. The cover
of the field is described always. Inside the critical period the change over
the last weeks and the comparison with earlier years of the same crop are
added, with what they say next to the water deficit of the balance. Outside
the crop season, and for the field without a crop, the reading describes only
the cover of the field.

The reading never changes the result of the consistency check: this
comparison always ends without a result. What it would say is kept in the
facts of the comparison (`satellite_signal`, `satellite_crop_mismatch`).
"""

from datetime import date, timedelta
from typing import Literal

from app.catalog.crop_model import CatalogCrop
from app.catalog.periods import DateRange
from app.contracts.analyses import CropHistory
from app.contracts.report import Limitation
from app.contracts.source_data import SatelliteData, SatelliteScene
from app.contracts.verdicts import ConsistencyItem
from app.engine import satellite_texts as texts
from app.engine.consistency_params import ConsistencyParams
from app.engine.consistency_parts import NO_DATA, NO_EFFECT, Comparison, period, pl
from app.engine.findings import Finding
from app.engine.satellite_crops import crop_reading
from app.engine.satellite_reading import Reading, read_satellite

# Where the analysis date lies for the crop.
SeasonState = Literal["in_season", "out_of_season", "no_crop"]

SOURCE = texts.SOURCE


def scene_values(scene: SatelliteScene) -> str:
    """Both indices of the scene as shown to the user."""
    return texts.values(scene)


def usable(scene: SatelliteScene) -> bool:
    """True when the scene has at least one of the two indices."""
    return scene.ndvi is not None or scene.ndmi is not None


def _item(span: str, value: str, meaning: str) -> ConsistencyItem:
    return ConsistencyItem(
        source=SOURCE, period=span, value=value, meaning=f"{meaning} {NO_EFFECT}"
    )


def _finding(reading: Reading, season_state: SeasonState) -> Finding | None:
    """What the reading means for the confidence; None when nothing."""
    if reading.crop_mismatch:
        return Finding(
            limitation=Limitation(
                text=texts.crop_mismatch(reading.april_ndvi), affects="all", permanent=False
            ),
            reason="zdjęcia satelitarne z kwietnia nie pasują do Uprawy ozimej",
        )
    if season_state == "out_of_season" and reading.newest is not None:
        return Finding(
            limitation=Limitation(text=texts.OUT_OF_SEASON, affects="current", permanent=False),
            reason="poza Sezonem uprawy zdjęcia satelitarne opisują tylko pokrywę pola",
        )
    return None


def _facts(reading: Reading) -> dict:
    changes = {change.index: change.difference for change in reading.changes}
    years = reading.years
    return {
        "satellite_scene": None if reading.newest is None else reading.newest.date.isoformat(),
        "satellite_signal": reading.signal,
        "satellite_ndmi_change": changes.get("ndmi"),
        "satellite_ndvi_change": changes.get("ndvi"),
        "satellite_same_crop_years": None if years is None else len(years.years),
        "satellite_ndmi_vs_years": None if years is None else years.difference,
        "satellite_crop_mismatch": reading.crop_mismatch,
    }


def describe_satellite(
    satellite: SatelliteData | None,
    analysis_date: date,
    *,
    season_state: SeasonState,
    params: ConsistencyParams,
    crop: CatalogCrop,
    season: DateRange | None = None,
    history: CropHistory | None = None,
    deficit: bool | None = None,
) -> Comparison:
    """Items for the cover of the field, its change and earlier years; no result.

    `season` is the running season of the crop, `deficit` whether the balance
    finds a water deficit of the crop (None when it gives no such level).
    """
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
            facts={"satellite_scene": None, "satellite_signal": "no_data"},
        )
    rules = crop_reading(crop.id)
    reading = read_satellite(
        satellite,
        analysis_date,
        crop=crop,
        rules=rules,
        season=season,
        history=history,
        deficit=deficit,
        window_days=params.satellite_max_scene_age_days,
    )
    newest = reading.newest
    if newest is None:
        head = ConsistencyItem(
            source=SOURCE,
            period=span,
            value=NO_DATA,
            meaning="Brak odczytu satelitarnego z tego okresu.",
        )
        return Comparison(
            items=(head,),
            result=None,
            clause=f"Odczytu satelitarnego z okresu {span} nie ma.",
            facts=_facts(reading),
        )
    meaning = texts.cover_meaning(season_state, reading, rules)
    items = [_item(pl(newest.date), texts.values(newest), meaning)]
    clause = (
        f"Odczyt satelitarny z {pl(newest.date)} ({texts.values(newest)}) jest podany "
        f"opisowo i nie wpływa na wynik.{texts.COVER_ONLY[season_state]}"
    )
    if reading.interpreted:
        said = texts.SIGNAL.get(reading.signal, "")
        changed = f"{texts.change_meaning(reading)} {said}".strip()
        items.append(_item(span, texts.change_value(reading), changed))
        items.append(
            _item(texts.years_period(reading), texts.years_value(reading), texts.years_meaning_for(reading))
        )
        clause = f"{clause} {said}".strip()
    return Comparison(
        items=tuple(items),
        result=None,
        clause=clause,
        finding=_finding(reading, season_state),
        facts=_facts(reading),
    )

