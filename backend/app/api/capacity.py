"""Limit of analyses running at the same time in the whole service.

Every analysis calls all external sources and uses worker threads, so their
number is capped whoever starts them. A request that finds every slot taken
is refused at once with `503` and `Retry-After`; nothing is queued.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.api import limits
from app.api.errors import ApiError
from app.orchestrator import runtime
from app.orchestrator.service import Orchestrator


async def require_analysis_slot(
    request: Request, service: Annotated[Orchestrator, Depends(runtime.get_orchestrator)]
) -> None:
    """Dependency of the routes that start an analysis."""
    limit = request.app.state.rate_limiter.settings.max_concurrent_analyses
    if limit > 0 and service.running_count >= limit:
        raise ApiError(
            503,
            "analysis_capacity_reached",
            "Trwa teraz zbyt wiele analiz naraz. Spróbuj ponownie za chwilę.",
            headers={"Retry-After": str(limits.CAPACITY_RETRY_AFTER_S)},
        )
