"""Named parameters and wording of the analysis of waters around a parcel."""

from app.sources.hydro_params import CANAL, DITCH, WATER_BODY, WATERCOURSE

# Groups the rules ask about, each with the kinds of objects it gathers:
# a ditch is a drainage ditch or a canal, a watercourse a river or a stream.
GROUPS: dict[str, tuple[str, ...]] = {
    "ditch": (DITCH, CANAL),
    "watercourse": (WATERCOURSE,),
    "water_body": (WATER_BODY,),
}

# Kinds as named in the texts of the Report.
KIND_LABELS: dict[str, str] = {
    DITCH: "rów melioracyjny",
    CANAL: "kanał",
    WATERCOURSE: "ciek",
    WATER_BODY: "zbiornik wodny",
}
KIND_LABELS_GENITIVE: dict[str, str] = {
    DITCH: "rowu melioracyjnego",
    CANAL: "kanału",
    WATERCOURSE: "cieku",
    WATER_BODY: "zbiornika wodnego",
}

# PROVISIONAL: no source; an object lies on the side towards which the terrain
# falls when the direction to it differs from the downhill direction by no
# more than this angle (a quarter of the horizon centred on that direction).
DOWNHILL_SIDE_HALF_ANGLE_DEG: float = 45.0

# PROVISIONAL: no source; the near part of an object is what lies no farther
# from the parcel outline than its nearest point plus this distance. The side
# of the parcel is read from the middle of that part, and the near part of a
# ditch is the water retention site. It only marks where to look; it is not a
# size of anything.
NEAR_PART_SPAN_M: float = 50.0

# An object closer to the outline than this is treated as lying on the parcel
# or on its boundary (position accuracy of the data is not better).
ON_PARCEL_WITHIN_M: float = 0.5

# Decimal places of the coordinates of a site geometry (about 0.1 m).
COORDINATE_DECIMALS: int = 6

ON_PARCEL = "na Działce lub na jej granicy"
# Placeholders: {distance} whole metres, {side} adjective naming the side.
OFF_PARCEL = "{distance} m od granicy Działki, strona {side}"
OFF_PARCEL_NO_SIDE = "{distance} m od granicy Działki"
SITE_ID = "water_object"
# Placeholder: {kind} in the genitive.
SITE_LABEL = "Odcinek {kind} najbliższy Działce"
