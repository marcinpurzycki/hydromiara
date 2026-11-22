"""Maize, oilseed, root, legume and grassland entries of the crop catalogue.

Data only: values, their sources and the reasons of the provisional ones. Dates
are "MM-DD"; see `crop_build.build_crop` for the meaning of each argument.
"""

from app.catalog.crop_build import build_crop
from app.catalog.crop_sources import (
    CDR,
    CDR_LEGUMES,
    CDR_MAIZE,
    COBORU,
    FAO56_TABLE_12,
    FAO56_TABLE_22,
)

MAIZE = build_crop(
    id="maize",
    name="Kukurydza na ziarno",
    name_genitive="kukurydzy na ziarno",
    tile=True,
    drought_monitoring_group="kukurydza na ziarno",
    season=("04-28", "10-18"),
    stages=("05-12", "05-28", "07-07", "08-26"),
    maturity="09-24",
    critical_period=("07-01", "08-31"),
    kc=(0.3, 1.2, 0.6),
    root_depth_m=(1.0, 1.7),
    depletion_fraction=0.55,
    ky=1.25,
    dates_source=(
        f"{COBORU} (siew, wschody, zbiór, dojrzałość pełna = wschody + 135 dni); długości faz: "
        "FAO-56 tab. 11, Maize (grain), April, Idaho 30/40/50/50"
    ),
    kc_source=(
        f"{FAO56_TABLE_12}: Maize, Field (grain); Kc end 0,60 = zbiór przy wysokiej wilgotności "
        "ziarna (przypis 11; COBORU: 28% przy zbiorze)"
    ),
    root_source=f"{FAO56_TABLE_22}: Maize, Field (grain)",
    critical_source=CDR_MAIZE,
)

MAIZE_SILAGE = build_crop(
    id="maize_silage",
    name="Kukurydza na kiszonkę",
    name_genitive="kukurydzy na kiszonkę",
    drought_monitoring_group="kukurydza na kiszonkę",
    season=("04-28", "09-09"),
    stages=("05-12", "05-28", "07-07", "08-26"),
    critical_period=("07-01", "08-31"),
    kc=(0.3, 1.2, 1.05),
    root_depth_m=(1.0, 1.7),
    depletion_fraction=0.55,
    ky=1.25,
    dates_source=(
        f"{COBORU} (siew, wschody, zbiór grupy średniowczesnej); fazy jak kukurydza na ziarno"
    ),
    kc_source=(
        f"{FAO56_TABLE_12}: Maize, Field (grain) do zbioru; Kc w dniu zbioru z krzywej kukurydzy "
        "na ziarno = 1.04, zaokrąglone do 1,05 (tyle samo: Maize, Sweet, zbiór na świeżo)"
    ),
    root_source=f"{FAO56_TABLE_22}: Maize, Field (grain)",
    critical_source=CDR_MAIZE,
    note="krzywa kukurydzy na ziarno ucięta w dniu zbioru zielonej masy",
)

# PROVISIONAL: start of the late stage follows the cereal rule (no source); Kc mid chosen
# inside the tabulated range.
WINTER_RAPESEED = build_crop(
    id="winter_rapeseed",
    name="Rzepak ozimy",
    name_genitive="rzepaku ozimego",
    tile=True,
    conditional=True,
    drought_monitoring_group="rzepak i rzepik",
    season=("08-30", "07-20"),
    stages=("09-11", "03-10", "04-25", "06-03"),
    maturity="07-03",
    critical_period=("04-10", "05-31"),
    kc=(0.35, 1.15, 0.35),
    root_depth_m=(1.0, 1.5),
    depletion_fraction=0.6,
    dates_source=(
        f"{COBORU}; początek fazy końcowej = dojrzałość techniczna - 30 dni (ROBOCZE: FAO-56 tab. "
        "11 nie ma rzepaku, przyjęto regułę zbóż)"
    ),
    kc_source=(
        f"{FAO56_TABLE_12}: Rapeseed, Canola; Kc ini grupy Oil Crops; Kc mid górna wartość zakresu "
        "1,0-1,15 (przypis 9: niższa dla rzadkich łanów)"
    ),
    root_source=f"{FAO56_TABLE_22}: Rapeseed, Canola",
    critical_source=(
        f"{CDR}, s. 233 (pąkowanie, kwitnienie, zawiązywanie łuszczyn) i tab. 8 (Drupka 1980: "
        "10-25 IV, 15-31 V)"
    ),
    note="jedna wartość robocza: początek fazy końcowej; wybór Kc mid wewnątrz zakresu",
    provisional={
        "stages": (
            "wartość robocza: początek fazy końcowej (FAO-56 tab. 11 nie ma rzepaku, przyjęto "
            "regułę zbóż)"
        ),
        "kc_mid": "wybór Kc mid wewnątrz zakresu 1,0-1,15",
    },
)

POTATO = build_crop(
    id="potato",
    name="Ziemniak",
    name_genitive="ziemniaka",
    drought_monitoring_group="ziemniak",
    season=("04-20", "09-24"),
    stages=("05-20", "05-20", "06-24", "08-13"),
    maturity="09-12",
    critical_period=("06-11", "07-31"),
    kc=(0.5, 1.15, 0.75),
    root_depth_m=(0.4, 0.6),
    depletion_fraction=0.35,
    ky=1.1,
    dates_source=(
        f"{COBORU} (sadzenie i zbiór, odmiany jadalne średnio wczesne i średnio późne); długości "
        "faz: FAO-56 tab. 11, Potato, April, Europe 30/35/50/30"
    ),
    kc_source=f"{FAO56_TABLE_12}: Potato; Kc ini grupy Roots and Tubers",
    root_source=f"{FAO56_TABLE_22}: Potato",
    critical_source=f"{CDR}, s. 227 (za Nowak 2006), ziemniak średniowczesny",
    note="siew = sadzenie; ziemniak późny: Okres krytyczny lipiec-sierpień",
)

SUGAR_BEET = build_crop(
    id="sugar_beet",
    name="Burak cukrowy",
    name_genitive="buraka cukrowego",
    drought_monitoring_group="burak cukrowy",
    season=("04-12", "10-18"),
    stages=("04-27", "06-03", "07-15", "09-06"),
    critical_period=("06-15", "09-15"),
    kc=(0.35, 1.2, 0.7),
    root_depth_m=(0.7, 1.2),
    depletion_fraction=0.55,
    ky=1.0,
    dates_source=(
        f"{COBORU} (siew, wschody, zbiór); długości faz: FAO-56 tab. 11, Sugarbeet, April, Idaho "
        "50/40/50/40, przeskalowane x1.05 do 189 dni"
    ),
    kc_source=(
        f"{FAO56_TABLE_12}: Sugar Beet; Kc end 0,70 bez nawadniania w ostatnim miesiącu (przypis "
        "5)"
    ),
    root_source=f"{FAO56_TABLE_22}: Sugar Beet",
    critical_source=f"{CDR}, s. 228",
    note=(
        "IUNG: na glebie kategorii I uprawa niewskazana; data zwarcia rzędów w Polsce nieustalona"
    ),
)

PEA = build_crop(
    id="pea",
    name="Groch siewny",
    name_genitive="grochu siewnego",
    drought_monitoring_group="rośliny strączkowe",
    season=("04-02", "07-26"),
    stages=("04-21", "04-21", "06-06", "07-06"),
    maturity="07-13",
    critical_period=("05-10", "06-30"),
    kc=(0.4, 1.15, 0.3),
    root_depth_m=(0.6, 1.0),
    depletion_fraction=0.4,
    ky=1.15,
    dates_source=COBORU,
    kc_source=f"{FAO56_TABLE_12}: Peas, Dry/Seed; Kc ini grupy Legumes",
    root_source=f"{FAO56_TABLE_22}: Peas, Dry/Seed",
    critical_source=CDR_LEGUMES,
)

FIELD_BEAN = build_crop(
    id="field_bean",
    name="Bobik",
    name_genitive="bobiku",
    drought_monitoring_group="rośliny strączkowe",
    season=("04-02", "08-12"),
    stages=("04-24", "04-24", "06-01", "07-20"),
    maturity="07-30",
    critical_period=("05-10", "06-30"),
    kc=(0.5, 1.15, 0.3),
    root_depth_m=(0.5, 0.7),
    depletion_fraction=0.45,
    dates_source=COBORU,
    kc_source=f"{FAO56_TABLE_12}: Fababean (broad bean), Dry/Seed",
    root_source=f"{FAO56_TABLE_22}: Fababean, Dry/Seed",
    critical_source=CDR_LEGUMES,
)

# PROVISIONAL: a perennial plant described with the sowing-to-harvest model; the start
# of the late stage is a working value.
GRASSLAND = build_crop(
    id="grassland",
    name="Łąka lub pastwisko",
    name_genitive="łąki lub pastwiska",
    conditional=True,
    perennial=True,
    season=("04-01", "09-30"),
    stages=("04-11", "04-11", "05-01", "09-20"),
    critical_period=("05-10", "09-15"),
    kc=(0.95, 1.05, 1.0),
    root_depth_m=(0.6, 1.0),
    depletion_fraction=0.6,
    dates_source=(
        f"{CDR}, tab. 7 (okres wegetacji IV-IX, za Ostrowski i in. 2008); FAO-56 tab. 11, Grass "
        "Pasture: L_ini 10, L_dev 20 dni; początek fazy końcowej ROBOCZY (10 dni przed końcem)"
    ),
    kc_source=f"{FAO56_TABLE_12}: Rye Grass hay, averaged cutting effects",
    root_source=f"{FAO56_TABLE_22}: Rye Grass hay",
    critical_source=f"{CDR}, tab. 8 (Drupka 1980: łąki trzykośne, pastwiska kwaterowe)",
    note=(
        "roślina wieloletnia: siew = początek, zbiór = koniec okresu wegetacji; poza sezonem pole "
        "nie jest gołe"
    ),
    provisional={
        "season": (
            "roślina wieloletnia: siew = początek, zbiór = koniec okresu wegetacji; poza sezonem "
            "pole nie jest gołe"
        ),
        "stages": (
            "roślina wieloletnia: siew = początek, zbiór = koniec okresu wegetacji; początek fazy "
            "końcowej roboczy (10 dni przed końcem)"
        ),
    },
)

CROPS = (MAIZE, MAIZE_SILAGE, WINTER_RAPESEED, POTATO, SUGAR_BEET, PEA, FIELD_BEAN, GRASSLAND)
