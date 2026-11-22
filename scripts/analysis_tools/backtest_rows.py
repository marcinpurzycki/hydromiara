"""One row of the backtest table for one analysis.

The row is read from the finished Report (verdicts, confidence, consistency
check, causes, sources) and from the stored outcome of every source (times).
A verdict the Report marks as not assessed gets an empty deficit level, never
the technical zero the Report carries. A failed analysis gives a row with the
reason and empty result columns.
"""

from collections.abc import Mapping, Sequence

from analysis_tools.runner import AnalysisResult
from analysis_tools.service import RunInfo, timestamp
from analysis_tools.tables import joined, markdown_table
from app.contracts.report import Report
from app.orchestrator.params import ANALYSIS_BUDGET_S

# Data categories in the order of the source registry.
TOPICS = ("parcel", "weather", "soil", "terrain", "satellite", "hydro", "drought_background")
TOPIC_FIELDS = ("chain_step", "s", "data_date")

KEY_COLUMNS = ("parcel_id", "crop_id", "analysis_date")
COLUMNS = (
    "label", "region", *KEY_COLUMNS,
    # done or failed; the reason of a failure; time from the request to the end.
    "status", "failure", "total_s", "within_budget",
    # True when either verdict shows a deficit (level 1 or more).
    "any_deficit",
    "current_level", "current_label", "current_assessed", "current_confidence",
    "season_state",
    "multiyear_deficit_years", "multiyear_total_years", "multiyear_level",
    "multiyear_confidence", "multiyear_deficit_year_list", "multiyear_year_list",
    # The independent drought indicator of the compared ten-day period.
    "consistency_result", "cdi_dekad", "cdi_class", "cdi_result", "satellite_scene",
    "causes_found", "causes_without_data", "recommendations", "irrigation_justified",
    "water_capacity_source", "available_water_mm", "limitations",
    "sources_answered", "sources_missing",
    *(f"{topic}_{name}" for topic in TOPICS for name in TOPIC_FIELDS),
    "source_notes", "fetched_at",
    "started_at", "mode", "host", "code_version",
)  # fmt: skip

MARKDOWN_HEADERS = (
    "Label", "Parcel", "Crop", "Analysis date", "Current water status", "Confidence",
    "Deficit years", "Confidence (multi-year)", "CDI class (ten-day period from)",
    "Consistency check", "Causes found", "Sources without data", "Time [s]",
)  # fmt: skip


def _trace(report: Report, rule_id: str) -> Mapping[str, object]:
    for entry in report.trace:
        if entry.rule_id == rule_id:
            return entry.values
    return {}


def _verdicts(report: Report) -> dict[str, object]:
    current, multiyear = report.current_status, report.multiyear_susceptibility
    current_assessed = current.details.get("assessed", True) is not False
    multiyear_assessed = multiyear.total_years > 0
    levels = [
        current.deficit_level if current_assessed else None,
        multiyear.deficit_level if multiyear_assessed else None,
    ]
    known = [level for level in levels if level is not None]
    return {
        "any_deficit": any(level >= 1 for level in known) if known else None,
        "current_level": levels[0],
        "current_label": current.label,
        "current_assessed": current_assessed,
        "current_confidence": current.confidence.level,
        "season_state": _trace(report, "season.state").get("season_state"),
        "multiyear_deficit_years": multiyear.deficit_years if multiyear_assessed else None,
        "multiyear_total_years": multiyear.total_years,
        "multiyear_level": levels[1],
        "multiyear_confidence": multiyear.confidence.level,
        "multiyear_deficit_year_list": joined(y.year for y in multiyear.years if y.deficit),
        "multiyear_year_list": joined(y.year for y in multiyear.years),
    }


def _findings(report: Report) -> dict[str, object]:
    check = _trace(report, "consistency_check.result")
    capacity = _trace(report, "root_zone.capacity")
    causes = report.causes
    return {
        "consistency_result": report.consistency_check.result,
        "cdi_dekad": check.get("cdi_dekad"),
        "cdi_class": check.get("cdi_class"),
        "cdi_result": check.get("cdi_result"),
        "satellite_scene": check.get("satellite_scene"),
        "causes_found": joined(cause.id for cause in causes if cause.found),
        "causes_without_data": joined(
            cause.id for cause in causes if not cause.found and cause.indicator.value is None
        ),
        "recommendations": joined(
            item.id for cause in causes for item in cause.recommendations
        ),
        "irrigation_justified": report.irrigation.justified,
        "water_capacity_source": capacity.get("capacity_source"),
        "available_water_mm": capacity.get("total_available_water_mm"),
        "limitations": sum(1 for item in report.limitations if not item.permanent),
    }


def _sources(result: AnalysisResult) -> dict[str, object]:
    """Which sources answered, from which chain link, how long each took."""
    report = result.report
    row: dict[str, object] = {}
    listed = {source.topic: source for source in report.sources}
    outcomes = {outcome.topic: outcome for outcome in result.outcomes}
    answered, missing, notes = [], [], []
    for topic in TOPICS:
        source, outcome = listed.get(topic), outcomes.get(topic)
        if source is None:
            # Not connected to the analysis: no entry among the Report's sources.
            missing.append(topic)
            continue
        if source.missing:
            missing.append(topic)
        else:
            answered.append(topic)
            row[f"{topic}_chain_step"] = source.chain_step
        row[f"{topic}_data_date"] = source.data_date
        if outcome is not None:
            row[f"{topic}_s"] = outcome.duration_s
            if outcome.message and source.missing:
                notes.append(f"{topic}: {outcome.message}")
    if not result.outcomes:
        # Over HTTP the reasons are only in the notes of the status.
        for item in (result.status or {}).get("sources", []):
            if item.get("state") == "missing" and item.get("note"):
                notes.append(f"{item['id']}: {item['note']}")
    fetched = [source.fetched_at for source in report.sources if source.fetched_at]
    row.update(
        sources_answered=joined(answered),
        sources_missing=joined(missing),
        source_notes=" / ".join(notes),
        fetched_at=timestamp(max(fetched)) if fetched else "",
    )
    return row


def result_row(result: AnalysisResult, run: RunInfo) -> dict[str, object]:
    """The table row of an analysis, whatever its end."""
    source = result.row
    row: dict[str, object] = {
        "label": source.label,
        "region": source.region,
        "parcel_id": source.parcel_id,
        "crop_id": source.crop_id,
        "analysis_date": source.analysis_date.isoformat(),
        "status": result.state,
        "failure": result.failure,
        "total_s": None if result.total_s is None else round(result.total_s, 2),
        "started_at": timestamp(result.started_at),
        "mode": run.mode,
        "host": run.host,
        "code_version": run.code_version,
    }
    if result.report is None:
        return row
    row["within_budget"] = result.total_s is not None and result.total_s <= ANALYSIS_BUDGET_S
    row.update(_verdicts(result.report))
    row.update(_findings(result.report))
    row.update(_sources(result))
    return row


def _markdown_row(row: Mapping[str, str]) -> Sequence[str]:
    if row["status"] != "done":
        failed = f"analysis failed: {row['failure']}"
        return (row["label"], row["parcel_id"], row["crop_id"], row["analysis_date"], failed,
                "", "", "", "", "", "", "", row["total_s"])  # fmt: skip
    years = ""
    if row["multiyear_deficit_years"]:
        years = f"{row['multiyear_deficit_years']} of {row['multiyear_total_years']}"
    cdi = f"{row['cdi_class']} ({row['cdi_dekad']})" if row["cdi_class"] else "no data"
    return (
        row["label"], row["parcel_id"], row["crop_id"], row["analysis_date"],
        row["current_label"], row["current_confidence"], years, row["multiyear_confidence"],
        cdi, row["consistency_result"], row["causes_found"].replace(";", ", "),
        row["sources_missing"].replace(";", ", "), row["total_s"],
    )  # fmt: skip


def markdown(rows: Sequence[Mapping[str, str]]) -> str:
    """The short table for a document: verdicts, drought indicator, consistency, time."""
    return markdown_table(MARKDOWN_HEADERS, [_markdown_row(row) for row in rows])
