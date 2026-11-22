"""Field vegetables of the crop catalogue.

Data only: values, their sources and the reasons of the provisional ones. Dates
are "MM-DD"; see `crop_build.build_crop` for the meaning of each argument.
"""

from app.catalog.crop_build import build_crop
from app.catalog.crop_sources import (
    CDR_VEGETABLES,
    COBORU_VEGETABLES,
    FAO56_TABLE_12,
    FAO56_TABLE_22,
)

# PROVISIONAL: dates from one year of trials, stage lengths from another climate, one
# critical period shared by all vegetables.
ONION = build_crop(
    id="onion",
    name="Cebula",
    name_genitive="cebuli",
    conditional=True,
    drought_monitoring_group="warzywa gruntowe",
    season=("04-06", "09-11"),
    stages=("04-22", "04-22", "05-18", "08-17"),
    critical_period=("04-15", "09-11"),
    kc=(0.7, 1.05, 0.75),
    root_depth_m=(0.3, 0.6),
    depletion_fraction=0.3,
    ky=1.1,
    dates_source=(
        f"{COBORU_VEGETABLES}, cebula z siewu, odmiany średniopóźne i późne, rok 2025, 6 stacji "
        "(siew, początek załamywania szczypioru = początek fazy końcowej, ostatni zbiór); "
        "długości faz: FAO-56 tab. 11, Onion (dry), April, Mediterranean 15/25/70/40, "
        "przeskalowane x1.05 do 158 dni"
    ),
    kc_source=f"{FAO56_TABLE_12}: Onions, dry; Kc ini grupy Small Vegetables",
    root_source=f"{FAO56_TABLE_22}: Onions, dry",
    critical_source=CDR_VEGETABLES,
    note="daty z jednego roku (2025); Okres krytyczny wspólny dla warzyw",
    provisional={
        "season": "daty z jednego roku (2025)",
        "stages": "daty z jednego roku (2025); długości faz z tabeli FAO-56 dla innego klimatu",
        "critical_period": "Okres krytyczny wspólny dla warzyw",
    },
)

# PROVISIONAL: dates from one year of trials, stage lengths from another climate, one
# critical period shared by all vegetables.
CABBAGE = build_crop(
    id="cabbage",
    name="Kapusta głowiasta",
    name_genitive="kapusty głowiastej",
    conditional=True,
    drought_monitoring_group="warzywa gruntowe",
    season=("05-18", "09-26"),
    stages=("06-19", "06-19", "08-05", "09-14"),
    critical_period=("05-18", "09-26"),
    kc=(0.7, 1.05, 0.95),
    root_depth_m=(0.5, 0.8),
    depletion_fraction=0.45,
    ky=0.95,
    dates_source=(
        f"{COBORU_VEGETABLES}, kapusta głowiasta biała, odmiany późne, rok 2025, 6 stacji "
        "(sadzenie, zbiór); długości faz: FAO-56 tab. 11, Cabbage, Sept, Calif. Desert "
        "40/60/50/15, przeskalowane x0.79 do 131 dni"
    ),
    kc_source=f"{FAO56_TABLE_12}: Cabbage; Kc ini grupy Small Vegetables",
    root_source=f"{FAO56_TABLE_22}: Cabbage",
    critical_source=CDR_VEGETABLES,
    note=(
        "siew = sadzenie rozsady; daty z jednego roku (2025); odmiany wczesne: sadzenie 30.04, "
        "zbiór 1-24.07; wiersz tabeli 11 z innego klimatu; Okres krytyczny wspólny dla warzyw"
    ),
    provisional={
        "season": "daty z jednego roku (2025)",
        "stages": "daty z jednego roku (2025); wiersz tabeli 11 z innego klimatu",
        "critical_period": "Okres krytyczny wspólny dla warzyw",
    },
)

# PROVISIONAL: dates from one year of trials, stage lengths scaled more than twofold,
# one critical period shared by all vegetables.
BEETROOT = build_crop(
    id="beetroot",
    name="Burak ćwikłowy",
    name_genitive="buraka ćwikłowego",
    conditional=True,
    drought_monitoring_group="warzywa gruntowe",
    season=("05-11", "10-07"),
    stages=("06-12", "06-12", "08-04", "09-16"),
    critical_period=("05-11", "09-30"),
    kc=(0.5, 1.05, 0.95),
    root_depth_m=(0.6, 1.0),
    depletion_fraction=0.5,
    dates_source=(
        f"{COBORU_VEGETABLES}, rok 2025, 6 stacji (siew, ostatni zbiór); długości faz: FAO-56 tab. "
        "11, Beets, table, Apr/May, Mediterranean 15/25/20/10, przeskalowane x2.13 do 149 dni"
    ),
    kc_source=f"{FAO56_TABLE_12}: Beets, table; Kc ini grupy Roots and Tubers",
    root_source=f"{FAO56_TABLE_22}: Beets, table",
    critical_source=CDR_VEGETABLES,
    note=(
        "daty z jednego roku (2025); wiersz tabeli 11 dotyczy uprawy 70-dniowej, skalowanie ponad "
        "dwukrotne; Okres krytyczny wspólny dla warzyw"
    ),
    provisional={
        "season": "daty z jednego roku (2025)",
        "stages": (
            "daty z jednego roku (2025); wiersz tabeli 11 dotyczy uprawy 70-dniowej, skalowanie "
            "ponad dwukrotne"
        ),
        "critical_period": "Okres krytyczny wspólny dla warzyw",
    },
)

# PROVISIONAL: stage lengths from another climate, Kc end chosen inside the tabulated
# range, one critical period shared by all vegetables.
TOMATO = build_crop(
    id="tomato",
    name="Pomidor gruntowy",
    name_genitive="pomidora gruntowego",
    conditional=True,
    drought_monitoring_group="warzywa gruntowe",
    season=("05-26", "10-02"),
    stages=("06-22", "06-22", "07-27", "09-05"),
    critical_period=("05-26", "09-30"),
    kc=(0.6, 1.15, 0.8),
    root_depth_m=(0.7, 1.5),
    depletion_fraction=0.4,
    ky=1.05,
    dates_source=(
        f"{COBORU_VEGETABLES}, pomidor uprawiany w polu, średnia z lat 2021-2025, 6 stacji "
        "(sadzenie, ostatni zbiór); długości faz: FAO-56 tab. 11, Tomato, April/May, "
        "Mediterranean 30/40/45/30, przeskalowane x0.89 do 129 dni"
    ),
    kc_source=(
        f"{FAO56_TABLE_12}: Tomato; Kc ini grupy Solanum Family; Kc end 0,80 = wartość grupy, "
        "wewnątrz zakresu gatunku 0,70-0,90"
    ),
    root_source=f"{FAO56_TABLE_22}: Tomato",
    critical_source=CDR_VEGETABLES,
    note=(
        "siew = sadzenie rozsady; pierwszy zbiór średnio 24.07; Okres krytyczny wspólny dla "
        "warzyw"
    ),
    provisional={
        "stages": "długości faz z tabeli FAO-56 dla innego klimatu",
        "critical_period": "Okres krytyczny wspólny dla warzyw",
        "kc_end": "wartość grupy Solanum Family, wewnątrz zakresu gatunku 0,70-0,90",
    },
)

# PROVISIONAL: stage lengths from another climate, one critical period shared by all
# vegetables.
CUCUMBER = build_crop(
    id="cucumber",
    name="Ogórek gruntowy",
    name_genitive="ogórka gruntowego",
    conditional=True,
    drought_monitoring_group="warzywa gruntowe",
    season=("05-23", "08-15"),
    stages=("06-08", "06-08", "07-02", "08-03"),
    critical_period=("05-23", "08-15"),
    kc=(0.6, 1.0, 0.75),
    root_depth_m=(0.7, 1.2),
    depletion_fraction=0.5,
    dates_source=(
        f"{COBORU_VEGETABLES}, ogórek polowy do kwaszenia, średnia z lat 2021-2025, 6 stacji "
        "(siew, ostatni zbiór); długości faz: FAO-56 tab. 11, Cucumber, June/Aug, Arid Region "
        "20/30/40/15, przeskalowane x0.80 do 84 dni"
    ),
    kc_source=f"{FAO56_TABLE_12}: Cucumber, Fresh Market",
    root_source=f"{FAO56_TABLE_22}: Cucumber, Fresh Market",
    critical_source=CDR_VEGETABLES,
    note=(
        "pierwszy zbiór średnio 11.07; wiersz tabeli 11 z innego klimatu; Okres krytyczny wspólny "
        "dla warzyw"
    ),
    provisional={
        "stages": "wiersz tabeli 11 z innego klimatu",
        "critical_period": "Okres krytyczny wspólny dla warzyw",
    },
)

CROPS = (ONION, CABBAGE, BEETROOT, TOMATO, CUCUMBER)
