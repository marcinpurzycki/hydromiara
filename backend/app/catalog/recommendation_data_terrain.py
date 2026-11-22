"""Catalogue entries of landscape retention and of agrotechnics that rest on the terrain."""

from app.catalog.crop_model import Sourced
from app.catalog.recommendation_data_soil import BASIS, CDR, NWRM
from app.catalog.recommendation_model import (
    AllOf, Addition, AnyOf, CauseFound, CatalogRecommendation, Compare, Threshold,
)

_DEFICIT_2 = Sourced[Threshold](
    value=2, provisional="working value: the level named 'wyraźny niedobór'"
)
_DEFICIT_1 = Sourced[Threshold](
    value=1, provisional="working value: the lowest deficit level, as in the gate of the causes"
)
_SLOPE_10 = Sourced[Threshold](
    value=10, source="Nowocień, Wawer 2021, IUNG-PIB, s. 23: limit of ploughing across the slope"
)
_SLOPE_14 = Sourced[Threshold](
    value=14, source="ARiMR, Normy GAEC obowiązujące w 2026 r., norma GAEC 5"
)

LANDSCAPE_ENTRIES: tuple[CatalogRecommendation, ...] = (
    CatalogRecommendation(
        id="midfield_trees",
        title="Zadrzewienie śródpolne lub żywopłot",
        group="retencja krajobrazowa",
        causes=("runoff", "precipitation"),
        requires=("balance",),
        conditions=(
            AnyOf(
                conditions=(
                    CauseFound(cause="runoff"),
                    AllOf(
                        conditions=(
                            CauseFound(cause="precipitation"),
                            Compare(
                                fact="multiyear_deficit_level", op="ge", value=_DEFICIT_2,
                                wording="Podatność wieloletnia wskazuje co najmniej wyraźny niedobór",
                            ),
                        )
                    ),
                )
            ),
        ),
        text=(
            "Rozważ pas drzew lub krzewów albo żywopłot, przy spadku w poprzek kierunku "
            "spływu wody. To działanie na lata. Sadzenie drzew na własnym gruncie nie "
            "wymaga zgody wodnoprawnej; sprawdź u doradcy wpływ na dopłaty."
        ),
        gain=(
            "Zadrzewienie osłania Działkę przed wiatrem i obniża temperaturę, więc gleba "
            "traci mniej wody. Zatrzymuje spływ po powierzchni i śnieg, który topnieje wolniej."
        ),
        citation=(
            f"{CDR}, s. 86–88 (zadrzewienia śródpolne), s. 105–106 (agroleśnictwo); {BASIS}; "
            f"{NWRM}, środek A2 „Buffer strips and hedges”."
        ),
    ),
    CatalogRecommendation(
        id="grassed_runoff_path",
        title="Trwała okrywa trawiasta w linii spływu wody",
        group="retencja krajobrazowa",
        causes=("runoff",),
        requires=("terrain",),
        text=(
            "Teren Działki opada na {downhill_label} ze spadkiem {slope_pct}%. W najniższej "
            "części, gdzie zbiera się spływająca woda, rozważ trwały pas trawy zamiast uprawy."
        ),
        gain=(
            "Teren stale pokryty roślinnością spowalnia spływ i pozwala wodzie wsiąknąć. "
            "Chroni też glebę przed zmywaniem."
        ),
        citation=f"{CDR}, s. 84 (trwałe użytki zielone); {NWRM}, środek A1 „Meadows and pastures”.",
        retention_site="lowest_part",
    ),
)

AGROTECHNICS_ENTRIES: tuple[CatalogRecommendation, ...] = (
    CatalogRecommendation(
        id="contour_farming",
        title="Uprawa w poprzek spadku",
        group="agrotechnika",
        causes=("runoff",),
        requires=("terrain",),
        text=(
            "Teren Działki opada na {downhill_label} ze spadkiem {slope_pct}%. Prowadź orkę, "
            "siew i redliny w poprzek spadku, nie wzdłuż."
        ),
        additions=(
            Addition(
                text=(
                    "Przy takim spadku sama orka w poprzek stoku nie wystarczy, potrzebna jest "
                    "trwała okrywa lub pasy roślin."
                ),
                conditions=(
                    Compare(fact="slope_pct", op="gt", value=_SLOPE_10, wording="spadek powyżej 10%"),
                ),
            ),
            Addition(
                text=(
                    "Na gruntach ornych o takim nachyleniu norma GAEC 5 nie pozwala uprawiać "
                    "roślin w redlinach wzdłuż stoku ani zostawiać czarnego ugoru zimą."
                ),
                conditions=(
                    Compare(fact="slope_pct", op="ge", value=_SLOPE_14, wording="spadek co najmniej 14%"),
                ),
            ),
        ),
        gain=(
            "Bruzdy w poprzek stoku zatrzymują wodę, zamiast ją odprowadzać. Na zboczach "
            "o spadku do 10% orka jesienna w poprzek stoku zwiększa zapas wody w metrowej "
            "warstwie gleby po roztopach o kilkanaście do kilkudziesięciu milimetrów "
            "i kilkakrotnie zmniejsza zmywanie gleby."
        ),
        citation=(
            "Nowocień, Wawer 2021, „Poradnik dla rolników w zakresie przeciwdziałania erozji "
            f"gleb”, IUNG-PIB, s. 23; {NWRM}, środek A4 „Strip cropping along contours”."
        ),
    ),
    CatalogRecommendation(
        id="critical_period_watch",
        title="Obserwacja Uprawy w okresie największego zapotrzebowania na wodę",
        group="agrotechnika",
        causes=("precipitation", "crop_demand"),
        requires=("balance", "crop"),
        conditions=(
            Compare(
                fact="multiyear_deficit_level", op="ge", value=_DEFICIT_1,
                wording="Podatność wieloletnia wskazuje co najmniej lekki niedobór",
            ),
        ),
        text=(
            "Dla {crop_name_genitive} okres największego zapotrzebowania na wodę trwa od "
            "{critical_period_start} do {critical_period_end}. W {deficit_years} z "
            "{total_years} ocenionych lat wody brakowało właśnie wtedy. W tym czasie częściej "
            "sprawdzaj stan roślin i zapas wody w glebie."
        ),
        gain="Wcześniej zauważysz niedobór i zdążysz zareagować, na przykład nawodnieniem, jeśli masz taką możliwość.",
        citation=(
            "KOWR, zadanie konkursowe HackNation 2026, pkt 3.2 (przykład: szczególny "
            f"monitoring upraw w okresie największego ryzyka); {CDR}, s. 225–235 (okresy "
            "krytyczne upraw)."
        ),
    ),
)
