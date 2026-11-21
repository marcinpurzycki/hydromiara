"""The current water status set against the drought indicator of the same dekad.

The indicator is the Combined Drought Indicator (CDI) of the European Drought
Observatory, one class per ten-day period (dekad). The names of its classes
are the names used by its publisher; the verdict of the Report is never
called a drought.

Which dekad: the latest one that ended on or before the analysis date. The
dekad that contains the analysis date usually ends after it and is built from
later observations, so it is used only when the analysis date is its last
day. Nothing later is ever read.
"""

from datetime import date, timedelta
from typing import NamedTuple

from app.contracts.source_data import DroughtBackground
from app.contracts.verdicts import ConsistencyItem
from app.engine.consistency_params import ConsistencyParams
from app.engine.consistency_parts import NO_DATA, Comparison, gap_finding, period, pl
from app.engine.verdicts import CurrentVerdict
from app.sources.drought_files import CDI_CLASS_LABELS, dekad_start, next_dekad

SOURCE = "European Drought Observatory (EDO), wskaźnik suszy CDI"
_INDICATOR = "niezależny wskaźnik suszy CDI"
_CANNOT = "Bieżącej sytuacji wodnej nie można z nim zestawić w Sprawdzeniu zgodności."

_SIGNAL_MEANING = {
    "drought": "Wskaźnik wskazuje suszę w tej dekadzie.",
    "no_drought": "Wskaźnik nie wskazuje suszy w tej dekadzie.",
    "transitional": (
        "Klasa przejściowa: poprawa po suszy, która sama nie rozstrzyga, czy wody brakuje."
    ),
}
_OUT_OF_SEASON = (
    " Data analizy jest poza Sezonem uprawy, więc Stopień niedoboru dotyczy Zapasu wody "
    "w glebie, nie potrzeb rośliny."
)


class Dekad(NamedTuple):
    """A ten-day period; both ends are inclusive."""

    start: date
    end: date


def comparison_dekad(analysis_date: date) -> Dekad:
    """The latest dekad that ended on or before the analysis date."""
    start = dekad_start(analysis_date)
    end = next_dekad(start) - timedelta(days=1)
    if end > analysis_date:
        end = start - timedelta(days=1)
        start = dekad_start(end)
    return Dekad(start, end)


def _class_of(background: DroughtBackground | None, dekad: Dekad) -> int | None:
    if background is None:
        return None
    for entry in background.dekads:
        if entry.date == dekad.start:
            return entry.cdi_class
    return None


def _no_value(dekad: Dekad, meaning: str, clause_reason: str, **extra) -> Comparison:
    span = period(*dekad)
    return Comparison(
        items=(ConsistencyItem(source=SOURCE, period=span, value=NO_DATA, meaning=meaning),),
        result=None,
        clause=(
            f"Bieżącej sytuacji wodnej nie zestawiono z niezależnym wskaźnikiem suszy CDI: "
            f"{clause_reason}."
        ),
        facts={"cdi_dekad": dekad.start.isoformat(), "cdi_class": None, "cdi_result": None},
        **extra,
    )


def compare_cdi(
    background: DroughtBackground | None,
    verdict: CurrentVerdict,
    analysis_date: date,
    *,
    out_of_season: bool,
    params: ConsistencyParams,
) -> Comparison:
    """The indicator class of the comparison dekad against the current water status.

    `out_of_season` is True when the crop has a season and the analysis date
    lies outside it.
    """
    dekad = comparison_dekad(analysis_date)
    span = period(*dekad)
    if dekad.start < params.cdi_series_start:
        since = pl(params.cdi_series_start)
        return _no_value(
            dekad,
            f"Wskaźnik CDI jest dostępny od {since}; ta dekada jest wcześniejsza.",
            f"wskaźnik jest dostępny od {since}, a potrzebna dekada {span} jest wcześniejsza",
            finding=gap_finding(
                f"Niezależny wskaźnik suszy CDI jest dostępny od {since}, a dekada "
                f"potrzebna dla Daty analizy ({span}) jest wcześniejsza. {_CANNOT}",
                "niezależny wskaźnik suszy nie sięga tak daleko wstecz jak Data analizy",
            ),
            replaces_missing=True,
        )
    if background is None:
        return _no_value(
            dekad,
            "Brak wskaźnika CDI dla Działki i tej dekady.",
            f"wskaźnika nie ma dla Działki i dekady {span}",
        )
    cdi_class = _class_of(background, dekad)
    if cdi_class is None:
        return _no_value(
            dekad,
            "Wskaźnik CDI nie ma wartości dla tej dekady.",
            f"wskaźnik nie ma wartości dla dekady {span}",
            finding=gap_finding(
                f"Niezależny wskaźnik suszy CDI nie ma wartości dla dekady {span}. {_CANNOT}",
                "niezależny wskaźnik suszy nie ma wartości dla dekady Sprawdzenia zgodności",
            ),
        )

    name = CDI_CLASS_LABELS.get(cdi_class, "klasa nieopisana")
    named = f"klasa {cdi_class}: „{name}”"
    signal = params.cdi_class_signals.get(cdi_class, "transitional")
    facts = {"cdi_dekad": dekad.start.isoformat(), "cdi_class": cdi_class, "cdi_result": None}

    def described(note: str, clause: str, finding=None) -> Comparison:
        item = ConsistencyItem(
            source=SOURCE,
            period=span,
            value=f"klasa {cdi_class}: {name}",
            meaning=f"{_SIGNAL_MEANING[signal]} {note}",
        )
        return Comparison(items=(item,), result=None, clause=clause, finding=finding, facts=facts)

    if not verdict.assessed:
        return described(
            "Nie zestawiono z werdyktem: Bieżąca sytuacja wodna nie ma Stopnia niedoboru.", ""
        )
    if signal == "transitional":
        return described(
            "Nie zestawiono z werdyktem.",
            f"Bieżącej sytuacji wodnej nie zestawiono z niezależnym wskaźnikiem suszy CDI: "
            f"w dekadzie {span} ma on klasę przejściową ({named}), która nie rozstrzyga, "
            "czy wody brakuje.",
            gap_finding(
                f"Niezależny wskaźnik suszy CDI ma dla dekady {span} klasę przejściową "
                f"({named}), która nie rozstrzyga, czy wody brakuje. {_CANNOT}",
                "niezależny wskaźnik suszy ma klasę przejściową, której nie da się zestawić",
            ),
        )
    if out_of_season and not params.cdi_compared_out_of_season:
        return described(
            "Nie zestawiono z werdyktem: Data analizy jest poza Sezonem uprawy.",
            "Bieżącej sytuacji wodnej nie zestawiono z niezależnym wskaźnikiem suszy CDI: "
            "Data analizy jest poza Sezonem uprawy.",
        )

    deficit = verdict.deficit_level >= params.deficit_from_level
    drought = signal == "drought"
    result = "zgodne" if deficit == drought else "rozbieżne"
    label = f"„{verdict.label}”"
    if deficit and drought:
        clause = (
            f"Bieżąca sytuacja wodna ({label}) i {_INDICATOR} z dekady {span} ({named}) "
            "wskazują to samo: wody brakuje."
        )
    elif not deficit and not drought:
        clause = (
            f"Bieżąca sytuacja wodna ({label}) i {_INDICATOR} z dekady {span} ({named}) "
            "wskazują to samo: wody nie brakuje."
        )
    elif deficit:
        clause = (
            f"Bieżąca sytuacja wodna wskazuje niedobór wody ({label}), a {_INDICATOR} "
            f"z dekady {span} nie wskazuje suszy ({named})."
        )
    else:
        clause = (
            f"Bieżąca sytuacja wodna nie wskazuje niedoboru wody ({label}), a {_INDICATOR} "
            f"z dekady {span} wskazuje suszę ({named})."
        )
    item = ConsistencyItem(
        source=SOURCE,
        period=span,
        value=f"klasa {cdi_class}: {name}",
        meaning=(
            f"{_SIGNAL_MEANING[signal]} Bieżąca sytuacja wodna: {label}. "
            f"Wynik zestawienia: {result}."
        ),
    )
    return Comparison(
        items=(item,),
        result=result,
        clause=clause + (_OUT_OF_SEASON if out_of_season else ""),
        facts={**facts, "cdi_result": result},
    )
