"""Report parts that no module computes yet.

Each function returns the most explicit "not assessed yet" value the contract
allows and never a made-up result. When the module that owns a part arrives,
its call replaces the function here and its entry in `PENDING_PARTS`.
"""

from app.contracts.report import Limitation, Summary

# Names of the parts below as they appear in the limitation shown to the user.
PENDING_PARTS = (
    "podsumowania słownego",
)

REASON_PENDING = (
    "Uzasadnienie słowne nie jest jeszcze dostępne w tej wersji; liczby stojące za oceną "
    "są w szczegółach."
)


def pending_summary() -> Summary:
    return Summary(text="Podsumowanie nie jest jeszcze dostępne w tej wersji.", source="template")


def pending_limitation() -> Limitation:
    return Limitation(
        text=f"Ta wersja raportu nie wyznacza jeszcze: {', '.join(PENDING_PARTS)}.",
        # About parts of the Report, not about the data behind the verdicts.
        affects="recommendations",
        permanent=False,
    )
