"""Report parts that no module computes yet.

Each value is the most explicit "not assessed yet" text the contract allows
and never a made-up result. When the module that owns a part arrives, its
call replaces the value here.
"""

REASON_PENDING = (
    "Uzasadnienie słowne nie jest jeszcze dostępne w tej wersji; liczby stojące za oceną "
    "są w szczegółach."
)

