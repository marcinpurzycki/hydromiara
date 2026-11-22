"""Crop catalogue data: the closed list in the order shown to the user.

The entries themselves are in the `crop_data_*` modules; adding or correcting
a crop is a change of data only. Every value names its source (document and
table). A value taken by analogy or as a working value also carries a
`provisional` reason, and its entry is marked `conditional` and preceded by a
PROVISIONAL comment. A crop enters the list only with the complete set of
parameters.
"""

from app.catalog import crop_data_cereals, crop_data_field_crops, crop_data_vegetables
from app.catalog.crop_model import CatalogCrop, Sourced

# PROVISIONAL: crop coefficient of a field without plants (bare soil), used for
# the field without a crop and for every crop outside its season. FAO-56 gives
# no single tabulated value: chapter 11 takes Kc ini of chapter 6, which
# depends on how often the soil is wetted and on ET0.
BARE_SOIL_KC: Sourced[float] = Sourced[float](
    value=0.3,
    provisional=(
        "FAO-56 nie podaje jednej wartości tabelarycznej Kc gołej gleby (rozdz. 11: Kc = Kc ini "
        "zależne od częstości zwilżania i ET0); stała 0,3 mieści się w podanych tam zakresach"
    ),
)

BARE_FIELD = CatalogCrop(
    id="bare_field",
    name="Pole bez uprawy",
    name_genitive="pola bez uprawy",
    tile=True,
    growth=None,
)

# Order of the list shown to the user: cereals, other field crops, the spring
# cereal mix, vegetables, the field without a crop.
CROPS: tuple[CatalogCrop, ...] = (
    *(crop for crop in crop_data_cereals.CROPS if crop is not crop_data_cereals.CEREAL_MIX),
    *crop_data_field_crops.CROPS,
    crop_data_cereals.CEREAL_MIX,
    *crop_data_vegetables.CROPS,
    BARE_FIELD,
)
