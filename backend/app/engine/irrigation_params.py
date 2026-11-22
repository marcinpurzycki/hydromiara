"""Named parameters of the irrigation part of the Report.

Everything that decides the irrigation answer is listed here, so replacing a
working value is a change of data, not of code.

Method source: FAO-56 (Allen et al. 1998), chapter 8, section "Forecasting or
allocating irrigations": irrigations should be applied before or at the moment
the readily available soil water is depleted (Dr <= RAW), and the net
irrigation depth should be smaller than or equal to the root zone depletion
(I <= Dr), so that no water is lost to deep percolation.

The range of the amount follows from those two conditions and from the state
of the water balance on the analysis date alone:
- upper end: the whole root zone depletion Dr, which refills the root zone to
  field capacity (the largest net depth that stays in the root zone);
- lower end: Dr - RAW, which brings the depletion back to the readily
  available water, the point where the stress ends.
  PROVISIONAL: FAO-56 gives the condition Dr <= RAW, not a smallest dose; using
  the amount that just restores it as the lower end is a rule of this project.

Amounts are net: water that has to enter the soil. Application losses, system
efficiency and single-dose limits are not modelled.
"""

from dataclasses import dataclass

# PROVISIONAL: lowest deficit level of the current water status from which
# irrigation is called justified. The project decision is "not justified when
# there is no deficit"; that every level, the slight one included, justifies
# it has no source.
JUSTIFIED_FROM_LEVEL: int = 1

# Step the ends of the range are rounded to, mm. Presentation only: the lower
# end is rounded up and the upper end down, so the rounded range stays inside
# the range computed from the balance.
AMOUNT_STEP_MM: float = 1.0

# 1 mm of water on 1 ha is 10 m3: an identity of units, not a tuned value.
M3_PER_HA_PER_MM: float = 10.0


@dataclass(frozen=True)
class IrrigationParams:
    """The parameters above as one immutable object; defaults are the module values."""

    justified_from_level: int = JUSTIFIED_FROM_LEVEL
    amount_step_mm: float = AMOUNT_STEP_MM

    def __post_init__(self) -> None:
        if self.justified_from_level not in (1, 2, 3):
            raise ValueError("irrigation can be justified only from a deficit level 1-3")
        if self.amount_step_mm <= 0:
            raise ValueError("the rounding step must be positive")


DEFAULT_IRRIGATION_PARAMS = IrrigationParams()
