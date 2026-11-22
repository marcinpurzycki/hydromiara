"""Helpers for the crop history tests: made-up crops, scenes, courses."""

from datetime import date

from app.catalog.crop_model import CatalogCrop
from app.catalog.crops import get_crop
from app.contracts.analyses import CropHistory
from app.contracts.source_data import SatelliteData, SatelliteScene, SourceData
from app.engine.assessment import WaterAssessment, assess_water
from app.engine.history import CourseResult, historical_course
from tests.engine_helpers import WHEAT, recorded_soil, recorded_weather, source_data
from tests.season_helpers import SPRING

JUNE = date(2023, 6, 20)
WINDOW = tuple(range(2014, 2024))

SCENES = (
    SatelliteScene(date=date(2021, 6, 12), clear_share_pct=100.0, ndvi=0.74, ndmi=0.31),
    SatelliteScene(date=date(2022, 6, 3), clear_share_pct=95.0, ndvi=0.7, ndmi=None),
    SatelliteScene(date=date(2022, 6, 14), clear_share_pct=90.0, ndvi=0.62, ndmi=0.2),
    SatelliteScene(date=date(2023, 6, 9), clear_share_pct=100.0, ndvi=0.81, ndmi=0.52),
    # Without any index, and after the analysis date: never read.
    SatelliteScene(date=date(2020, 6, 10), clear_share_pct=100.0, ndvi=None, ndmi=None),
    SatelliteScene(date=date(2023, 6, 25), clear_share_pct=100.0, ndvi=0.2, ndmi=0.1),
)


def lookup(crop_id: str) -> CatalogCrop:
    """The catalogue plus the made-up spring crop of the tests."""
    return SPRING if crop_id == SPRING.id else get_crop(crop_id)


def data(*, satellite: bool = True, weather=None) -> SourceData:
    """Recorded weather and soil of the trial parcel, with or without scenes."""
    base = source_data(recorded_weather() if weather is None else weather, recorded_soil())
    if not satellite:
        return base
    return base.model_copy(update={"satellite": SatelliteData(scenes=list(SCENES))})


def course_of(
    history: CropHistory | None,
    *,
    crop: CatalogCrop = WHEAT,
    day: date = JUNE,
    source: SourceData | None = None,
) -> tuple[CourseResult | None, WaterAssessment]:
    source = data() if source is None else source
    assessment = assess_water(source, crop, day)
    return historical_course(source, assessment, crop, history, lookup=lookup), assessment


def years(**named: str) -> CropHistory:
    """`years(y2015="bare_field")` -> a history naming 2015."""
    return CropHistory(years={int(key[1:]): crop_id for key, crop_id in named.items()})


SAME = CropHistory(same_every_year=True)
