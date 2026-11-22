"""How the satellite reading is read for each crop. Data only, keyed by crop identifier.

The crop catalogue does not carry these properties, so they live here. A crop
without an entry gets the safe default: its reading is described, the change
of NDMI is shown, and nothing is concluded from it about a water deficit.
"""

from dataclasses import dataclass
from typing import Literal

Index = Literal["ndvi", "ndmi"]


@dataclass(frozen=True)
class CropReading:
    """Reading rules of one group of crops."""

    # Indices whose change over the last weeks is reported, in this order.
    change_indices: tuple[Index, ...] = ("ndmi",)
    # True when a fall of NDMI may be set against the water deficit of the balance.
    signals_deficit: bool = False
    # True for crops sown in autumn that cover the field in April.
    green_in_april: bool = False
    # Sentence for the Report on what must not be read as a water deficit.
    note: str | None = None
    source: str | None = None


DEFAULT = CropReading()

_CEREAL_NOTE = (
    "W zwartym łanie NDVI jest nasycony, dlatego o zawartości wody w roślinach mówi NDMI, "
    "a NDVI opisuje tylko pokrywę pola."
)
_CEREAL_SOURCE = "Jackson et al. 2004, Remote Sens. Environ. 92:475-482"

SPRING_CEREAL = CropReading(signals_deficit=True, note=_CEREAL_NOTE, source=_CEREAL_SOURCE)
WINTER_CEREAL = CropReading(
    signals_deficit=True, green_in_april=True, note=_CEREAL_NOTE, source=_CEREAL_SOURCE
)
RAPESEED = CropReading(
    signals_deficit=True,
    green_in_april=True,
    note=(
        "W czasie kwitnienia NDVI spada z powodu żółtych kwiatów, dlatego kierunek zmiany "
        "odczytujemy z NDMI."
    ),
    source="d'Andrimont et al. 2020, Remote Sens. Environ. 239:111660",
)
ROOT_CROP = CropReading(
    note=(
        "Dla tej Uprawy NDVI nie reaguje na warunki wodne wpływające na plon, dlatego NDMI "
        "podajemy tylko opisowo."
    ),
    source="Vannoppen and Gobin 2022, Water 14:1188",
)
GRASSLAND = CropReading(
    change_indices=("ndvi", "ndmi"),
    signals_deficit=True,
    note="Dla użytków zielonych NDVI i NDMI odczytujemy razem.",
    source="Bartold et al. 2024, Plants 13:2319",
)

BY_CROP: dict[str, CropReading] = {
    "winter_wheat": WINTER_CEREAL,
    "winter_rye": WINTER_CEREAL,
    "winter_triticale": WINTER_CEREAL,
    "winter_barley": WINTER_CEREAL,
    "spring_wheat": SPRING_CEREAL,
    "spring_barley": SPRING_CEREAL,
    "oats": SPRING_CEREAL,
    "cereal_mix": SPRING_CEREAL,
    "maize": SPRING_CEREAL,
    "maize_silage": SPRING_CEREAL,
    "winter_rapeseed": RAPESEED,
    "potato": ROOT_CROP,
    "sugar_beet": ROOT_CROP,
    "grassland": GRASSLAND,
}


def crop_reading(crop_id: str) -> CropReading:
    """Reading rules of the crop; the safe default for a crop without an entry."""
    return BY_CROP.get(crop_id, DEFAULT)
