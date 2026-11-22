"""Cereals of the crop catalogue.

Data only: values, their sources and the reasons of the provisional ones. Dates
are "MM-DD"; see `crop_build.build_crop` for the meaning of each argument.
"""

from app.catalog.crop_build import all_values, build_crop
from app.catalog.crop_sources import (
    CDR,
    CDR_CEREALS,
    COBORU,
    COBORU_CEREALS,
    FAO56_TABLE_12,
    FAO56_TABLE_22,
)

WINTER_WHEAT = build_crop(
    id="winter_wheat",
    name="Pszenica ozima",
    name_genitive="pszenicy ozimej",
    tile=True,
    drought_monitoring_group="zboża ozime",
    season=("10-05", "08-01"),
    stages=("10-19", "03-09", "05-28", "06-21"),
    maturity="07-21",
    critical_period=("05-11", "07-10"),
    kc=(0.4, 1.15, 0.25),
    root_depth_m=(1.5, 1.8),
    depletion_fraction=0.55,
    ky=1.05,
    dates_source=COBORU_CEREALS,
    kc_source=(
        f"{FAO56_TABLE_12}: Winter Wheat, with frozen soils; Kc end 0,25 = dolna wartość zakresu "
        "(przypis 10: wyższa dla zbioru ręcznego)"
    ),
    root_source=f"{FAO56_TABLE_22}: Winter Wheat",
    critical_source=CDR_CEREALS,
)

# PROVISIONAL: the source has no row for rye; winter wheat values taken by analogy.
WINTER_RYE = build_crop(
    id="winter_rye",
    name="Żyto ozime",
    name_genitive="żyta ozimego",
    tile=True,
    conditional=True,
    drought_monitoring_group="zboża ozime",
    season=("09-27", "08-01"),
    stages=("10-08", "03-11", "05-10", "06-19"),
    maturity="07-19",
    critical_period=("05-11", "07-10"),
    kc=(0.4, 1.15, 0.25),
    root_depth_m=(1.5, 1.8),
    depletion_fraction=0.55,
    dates_source=COBORU_CEREALS,
    kc_source=(
        f"{FAO56_TABLE_12}: grupa Cereals (Kc mid 1,15); Kc ini i Kc end jak Winter Wheat "
        "(analogia)"
    ),
    root_source=f"{FAO56_TABLE_22}: Winter Wheat (analogia)",
    critical_source=CDR_CEREALS,
    note="brak wiersza gatunku w FAO-56; wartości pszenicy ozimej przez analogię",
    provisional=dict.fromkeys(
        ("kc_ini", "kc_end", "root_depth_m", "depletion_fraction"),
        "brak wiersza gatunku w FAO-56; wartości pszenicy ozimej przez analogię",
    ),
)

# PROVISIONAL: the source has no row for triticale; winter wheat values taken by analogy.
WINTER_TRITICALE = build_crop(
    id="winter_triticale",
    name="Pszenżyto ozime",
    name_genitive="pszenżyta ozimego",
    conditional=True,
    drought_monitoring_group="zboża ozime",
    season=("09-30", "08-01"),
    stages=("10-11", "03-11", "05-20", "06-20"),
    maturity="07-20",
    critical_period=("05-11", "07-10"),
    kc=(0.4, 1.15, 0.25),
    root_depth_m=(1.5, 1.8),
    depletion_fraction=0.55,
    dates_source=COBORU_CEREALS,
    kc_source=(
        f"{FAO56_TABLE_12}: grupa Cereals (Kc mid 1,15); Kc ini i Kc end jak Winter Wheat "
        "(analogia)"
    ),
    root_source=f"{FAO56_TABLE_22}: Winter Wheat (analogia)",
    critical_source=CDR_CEREALS,
    note="brak wiersza gatunku w FAO-56; wartości pszenicy ozimej przez analogię",
    provisional=dict.fromkeys(
        ("kc_ini", "kc_end", "root_depth_m", "depletion_fraction"),
        "brak wiersza gatunku w FAO-56; wartości pszenicy ozimej przez analogię",
    ),
)

WINTER_BARLEY = build_crop(
    id="winter_barley",
    name="Jęczmień ozimy",
    name_genitive="jęczmienia ozimego",
    drought_monitoring_group="zboża ozime",
    season=("09-25", "07-11"),
    stages=("10-06", "03-10", "05-12", "06-02"),
    maturity="07-02",
    critical_period=("05-11", "07-10"),
    kc=(0.4, 1.15, 0.25),
    root_depth_m=(1.0, 1.5),
    depletion_fraction=0.55,
    dates_source=COBORU_CEREALS,
    kc_source=f"{FAO56_TABLE_12}: Barley; Kc ini 0,4 jak Winter Wheat, with frozen soils",
    root_source=f"{FAO56_TABLE_22}: Barley",
    critical_source=CDR_CEREALS,
    note=(
        "Kc ini zimą jak pszenica ozima (FAO-56 nie rozróżnia jęczmienia ozimego); Okres "
        "krytyczny wspólny dla zbóż ozimych, jęczmień kłosi się 16 dni wcześniej"
    ),
)

SPRING_WHEAT = build_crop(
    id="spring_wheat",
    name="Pszenica jara",
    name_genitive="pszenicy jarej",
    drought_monitoring_group="zboża jare",
    season=("03-28", "08-07"),
    stages=("04-15", "04-15", "06-10", "06-29"),
    maturity="07-29",
    critical_period=("05-21", "07-10"),
    kc=(0.3, 1.15, 0.25),
    root_depth_m=(1.0, 1.5),
    depletion_fraction=0.55,
    ky=1.15,
    dates_source=COBORU_CEREALS,
    kc_source=(
        f"{FAO56_TABLE_12}: Spring Wheat; Kc ini grupy Cereals; Kc end dolna wartość zakresu "
        "0,25-0,4"
    ),
    root_source=f"{FAO56_TABLE_22}: Spring Wheat",
    critical_source=CDR_CEREALS,
)

SPRING_BARLEY = build_crop(
    id="spring_barley",
    name="Jęczmień jary",
    name_genitive="jęczmienia jarego",
    tile=True,
    drought_monitoring_group="zboża jare",
    season=("03-29", "08-02"),
    stages=("04-14", "04-14", "06-06", "06-21"),
    maturity="07-21",
    critical_period=("05-21", "07-10"),
    kc=(0.3, 1.15, 0.25),
    root_depth_m=(1.0, 1.5),
    depletion_fraction=0.55,
    dates_source=COBORU_CEREALS,
    kc_source=f"{FAO56_TABLE_12}: Barley; Kc ini grupy Cereals",
    root_source=f"{FAO56_TABLE_22}: Barley",
    critical_source=CDR_CEREALS,
)

OATS = build_crop(
    id="oats",
    name="Owies",
    name_genitive="owsa",
    drought_monitoring_group="zboża jare",
    season=("03-28", "08-05"),
    stages=("04-14", "04-14", "06-08", "06-24"),
    maturity="07-24",
    critical_period=("05-21", "07-10"),
    kc=(0.3, 1.15, 0.25),
    root_depth_m=(1.0, 1.5),
    depletion_fraction=0.55,
    dates_source=COBORU_CEREALS,
    kc_source=f"{FAO56_TABLE_12}: Oats; Kc ini grupy Cereals",
    root_source=f"{FAO56_TABLE_22}: Oats",
    critical_source=CDR_CEREALS,
    note="faza środkowa od wiechowania",
)

# PROVISIONAL: every value taken by analogy to spring barley and oats.
CEREAL_MIX = build_crop(
    id="cereal_mix",
    name="Mieszanka zbożowa jara",
    name_genitive="mieszanki zbożowej jarej",
    conditional=True,
    drought_monitoring_group="zboża jare",
    season=("03-29", "08-04"),
    stages=("04-14", "04-14", "06-07", "06-23"),
    maturity="07-23",
    critical_period=("05-21", "07-10"),
    kc=(0.3, 1.15, 0.25),
    root_depth_m=(1.0, 1.5),
    depletion_fraction=0.55,
    dates_source=(
        f"{COBORU}: średnia dat jęczmienia jarego i owsa (ANALOGIA, mieszanek COBORU nie bada); "
        "początek fazy końcowej = dojrzałość pełna - 30 dni (FAO-56 tab. 11)"
    ),
    kc_source=f"{FAO56_TABLE_12}: Barley i Oats (wartości jednakowe); Kc ini grupy Cereals",
    root_source=f"{FAO56_TABLE_22}: Barley i Oats (wartości jednakowe)",
    critical_source=f"{CDR}, s. 229-230 (za Żarski 2006), zboża jare, gleby średnie",
    note="wszystkie wartości przez analogię do jęczmienia jarego i owsa",
    provisional=all_values("wszystkie wartości przez analogię do jęczmienia jarego i owsa"),
)

CROPS = (
    WINTER_WHEAT,
    WINTER_RYE,
    WINTER_TRITICALE,
    WINTER_BARLEY,
    SPRING_WHEAT,
    SPRING_BARLEY,
    OATS,
    CEREAL_MIX,
)
