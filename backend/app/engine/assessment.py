"""Water assessment of one crop on one parcel: balance plus the two verdicts.

The single entry point for callers that hold the source data of an analysis.
Running it again for another crop on the same data gives the comparison used
by the simulation. The two verdicts are returned side by side and are never
combined into one value.
"""

from dataclasses import dataclass
from datetime import date

from app.catalog.crop_model import CatalogCrop
from app.contracts.source_data import SourceData
from app.engine.balance import WaterBalance, run_balance
from app.engine.params import DEFAULT_PARAMS, EngineParams
from app.engine.root_zone import RootZone, root_zone
from app.engine.susceptibility import SusceptibilityVerdict, multiyear_susceptibility
from app.engine.verdicts import CurrentVerdict, current_status


@dataclass(frozen=True)
class WaterAssessment:
    crop_id: str
    analysis_date: date
    root_zone: RootZone
    balance: WaterBalance
    current_status: CurrentVerdict
    multiyear_susceptibility: SusceptibilityVerdict


def assess_water(
    source_data: SourceData,
    crop: CatalogCrop,
    analysis_date: date,
    params: EngineParams = DEFAULT_PARAMS,
    *,
    zone: RootZone | None = None,
) -> WaterAssessment:
    """Balance and both verdicts for the crop on the analysis date.

    Reads only the weather and the soil of the source data; soil may be
    missing. `zone` replaces the root zone derived from the soil and the crop.
    """
    used_zone = root_zone(source_data.soil, crop, params) if zone is None else zone
    balance = run_balance(source_data.weather.days, crop, used_zone, analysis_date, params)
    return WaterAssessment(
        crop_id=crop.id,
        analysis_date=analysis_date,
        root_zone=used_zone,
        balance=balance,
        current_status=current_status(balance, params),
        multiyear_susceptibility=multiyear_susceptibility(balance, crop, params),
    )
