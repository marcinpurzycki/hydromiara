"""Report parts that no module computes yet.

Each function returns the most explicit "not assessed yet" value the contract
allows and never a made-up result. When the module that owns a part arrives,
its call replaces the function here and its entry in `PENDING_PARTS`.

Two values could not be expressed as absent, because the contract has no such
state; they are open questions for both teams:
- `confidence.level` must be one of three words, so the lowest one is used
  together with a sentence saying that confidence is not determined;
- `irrigation.applicable` is filled from the crop season alone.
"""

from app.contracts.causes import Cause, Irrigation
from app.contracts.common import Confidence
from app.contracts.report import Limitation, Summary
from app.contracts.verdicts import ConsistencyCheck, HistoricalCourse

# Names of the parts below as they appear in the limitation shown to the user.
PENDING_PARTS = (
    "Pewności oceny",
    "Przyczyn niedoboru",
    "Rekomendacji",
    "zaleceń nawadniania",
    "Sprawdzenia zgodności",
    "podsumowania słownego",
)

REASON_PENDING = (
    "Uzasadnienie słowne nie jest jeszcze dostępne w tej wersji; liczby stojące za oceną "
    "są w szczegółach."
)


def pending_confidence() -> Confidence:
    # Placeholder: the contract has no "not determined" level.
    return Confidence(
        level="niska",
        why="Pewność oceny nie jest jeszcze wyznaczana w tej wersji; podano najniższy poziom.",
    )


def pending_summary() -> Summary:
    return Summary(text="Podsumowanie nie jest jeszcze dostępne w tej wersji.", source="template")


def pending_historical_course() -> HistoricalCourse | None:
    return None


def pending_causes() -> list[Cause]:
    return []


def pending_irrigation(in_season: bool) -> Irrigation:
    text = "Zalecenia nawadniania nie są jeszcze wyznaczane w tej wersji."
    return Irrigation(
        applicable=in_season,
        text=text,
        justified=None,
        amount_mm=None,
        amount_m3_ha=None,
        timing=None,
        reason_if_none=text,
    )


def pending_consistency_check() -> ConsistencyCheck:
    return ConsistencyCheck(
        result="brak danych",
        sentence=(
            "Sprawdzenie zgodności nie jest jeszcze wykonywane w tej wersji: analiza nie "
            "korzysta z niezależnego wskaźnika suszy ani z odczytu satelitarnego."
        ),
        items=[],
    )


def pending_limitation() -> Limitation:
    return Limitation(
        text=f"Ta wersja raportu nie wyznacza jeszcze: {', '.join(PENDING_PARTS)}.",
        affects="all",
        permanent=False,
    )
