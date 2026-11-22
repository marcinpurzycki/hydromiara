"""Report part that describes the data: the source list."""

from typing import Literal

from app.contracts.report import ReportSource
from app.contracts.source_data import SourceData, SourceOutcome, SourceTopic
from app.sources.hydro_params import BDOT_LOCAL_SOURCE_NAME, BDOT_SOURCE_NAME
from app.sources.terrain_params import GUGIK_SOURCE_NAME

Mode = Literal["na żywo", "plik lokalny"]
LIVE: Mode = "na żywo"
LOCAL_FILE: Mode = "plik lokalny"

# Name, licence and access mode per topic, as documented in the README source
# table. A topic gets its entry when its source is connected to the analysis.
_SOURCE_TERMS: dict[SourceTopic, tuple[str, str, Mode]] = {
    "parcel": ("ULDK GUGiK", "bezpłatnie, bez rejestracji; wymagane podanie źródła", LIVE),
    "weather": (
        "Open-Meteo, archiwum pogodowe",
        "CC BY 4.0, wymagane podanie źródła z odnośnikiem: Weather data by Open-Meteo.com "
        "(https://open-meteo.com/); bezpłatny dostęp tylko do zastosowań niekomercyjnych",
        LIVE,
    ),
    "soil": (
        "IUNG-PIB, mapa kategorii podatności gleb na suszę",
        "usługa publiczna i bezpłatna; warunków ponownego wykorzystania nie opublikowano; "
        "podajemy źródło",
        LIVE,
    ),
    "terrain": (
        "Copernicus DEM GLO-30",
        "bezpłatnie na warunkach licencji Copernicus DEM (GLO-30 Public); wymagane podanie "
        "źródła i informacji o prawach autorskich",
        LIVE,
    ),
    "satellite": (
        "Copernicus Sentinel-2 L2A",
        "bezpłatny, pełny i otwarty dostęp na warunkach noty prawnej danych Sentinel; "
        "wymagane podanie źródła i zaznaczenie przetworzenia danych",
        LIVE,
    ),
    "hydro": (
        BDOT_SOURCE_NAME,
        "bezpłatnie (Prawo geodezyjne i kartograficzne, art. 40a ust. 2 pkt 1 lit. h); "
        "podajemy źródło",
        LIVE,
    ),
    "drought_background": (
        "European Drought Observatory (EDO), Combined Drought Indicator (CDI)",
        "CC BY 4.0; wymagane podanie źródła i zaznaczenie zmian",
        LOCAL_FILE,
    ),
}
_UNKNOWN_TERMS: tuple[str, str, Mode] = ("źródło nieokreślone", "nie podano", LIVE)
# Chain links that read files kept on the server instead of asking a service.
_LOCAL_FILE_LINKS: frozenset[str] = frozenset({BDOT_LOCAL_SOURCE_NAME})

# Licence of a link of a substitute chain whose terms differ from those of
# the entry of its topic above, by the name of the link.
_LICENCE_BY_SOURCE_NAME: dict[str, str] = {
    GUGIK_SOURCE_NAME: (
        "dane numerycznego modelu terenu GUGiK: bezpłatnie, do dowolnego wykorzystania; "
        "podajemy źródło"
    ),
    # Soil substitute: texture maps.
    "ISRIC SoilGrids 2.0": "CC BY 4.0, wymagane podanie źródła",
}


def report_source(outcome: SourceOutcome) -> ReportSource:
    name, licence, mode = _SOURCE_TERMS.get(outcome.topic, _UNKNOWN_TERMS)
    licence = _LICENCE_BY_SOURCE_NAME.get(outcome.source_name or "", licence)
    return ReportSource(
        topic=outcome.topic,
        name=outcome.source_name or name,
        license=licence,
        mode=LOCAL_FILE if outcome.source_name in _LOCAL_FILE_LINKS else mode,
        data_date=outcome.data_date,
        fetched_at=outcome.fetched_at,
        # The contract needs a chain step even for a missing source; `missing` tells.
        chain_step=outcome.chain_step or 1,
        missing=not outcome.ok,
    )


def report_sources(source_data: SourceData) -> list[ReportSource]:
    return [report_source(outcome) for outcome in source_data.outcomes]
