"""The analysis of waters as parcel facts for the rules and as a trace entry.

Facts of a group are named `<group>_...` for the groups `ditch` (drainage
ditch or canal), `watercourse` (river or stream) and `water_body`:

- `<group>_distance_m`  distance from the parcel outline, whole metres,
- `<group>_side`        side of the parcel, e.g. "północna",
- `<group>_location`    both as a phrase for the texts,
- `<group>_downhill`    True when the object lies on the side towards which
                        the terrain falls; None without a downhill direction,
- `<group>_label`       what the object is, e.g. "rów melioracyjny",
- `<group>_name`        its name, when the data have one.

All facts of a group without an object in the data are None, so a rule about
that group is not met and no recommendation about it can appear.

Pure: no network, clock or files.
"""

from app.contracts.common import Scalar
from app.contracts.report import TraceEntry
from app.engine import water_params as params
from app.engine.water_analysis import WaterAnalysis

FACT_SUFFIXES: tuple[str, ...] = ("distance_m", "side", "location", "downhill", "label", "name")
COUNT_FACT = "water_objects_count"


def water_facts(analysis: WaterAnalysis) -> dict[str, Scalar]:
    """Values of every water fact; None for a group without objects."""
    values: dict[str, Scalar] = {COUNT_FACT: analysis.objects_count}
    for group in params.GROUPS:
        found = analysis.nearest.get(group)
        values |= {f"{group}_{suffix}": None for suffix in FACT_SUFFIXES}
        if found is None:
            continue
        values |= {
            f"{group}_distance_m": round(found.distance_m),
            f"{group}_side": found.side,
            f"{group}_location": found.location,
            f"{group}_downhill": found.downhill,
            f"{group}_label": found.label,
            f"{group}_name": found.name,
        }
    return values


def water_trace(analysis: WaterAnalysis) -> TraceEntry:
    """Which objects the rules about waters were decided on."""
    values = {
        name: value
        for name, value in water_facts(analysis).items()
        if not name.endswith(("_location", "_label"))
    }
    if analysis.nearest:
        found = ", ".join(
            f"{item.label} ({item.location})" for item in analysis.nearest.values()
        )
        result = f"najbliższe obiekty w danych: {found}"
    else:
        result = "w danych nie ma rowów, cieków ani zbiorników w otoczeniu Działki"
    return TraceEntry(
        rule_id="water.nearest",
        condition=(
            "najbliższy rów (rów melioracyjny lub kanał), ciek i zbiornik wodny z danych "
            "o wodach: odległość od granicy Działki, strona Działki i zgodność tej strony "
            "z kierunkiem, w którym opada teren (różnica kierunków najwyżej "
            f"{params.DOWNHILL_SIDE_HALF_ANGLE_DEG:.0f}°)"
        ),
        values=values,
        result=result,
    )
