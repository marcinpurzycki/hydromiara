"""Rule engine: from the found deficit causes to the recommendations of a Report.

Every catalogue entry is decided once, in catalogue order:

1. Without determined causes nothing is checked. An entry none of whose causes
   is found does not apply.
2. A required data topic without data: the rule is not run and a limitation
   says so. The same when a fact read by its conditions or texts is unknown.
3. All conditions hold: the entry is triggered and becomes a recommendation
   with the rule in words, the values that met it and its citation.

Placement. A recommendation appears once, under the strongest found cause it
answers (the first in the order of the causes in the Report). Under one cause
the groups follow the order of the Report (landscape retention, soil
retention, agronomy) and, within a group, the order of the catalogue.
Irrigation entries are never placed under a cause: they are returned apart,
because the Report speaks about irrigation in one place, at its end.

Every entry leaves one trace entry, triggered or not.

Pure and deterministic: no network, clock or files.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.catalog.recommendation_facts import (
    CAUSE_LABELS,
    FACTS,
    GROUP_ORDER,
    TOPIC_LABELS,
    DataTopic,
    SiteKind,
)
from app.catalog.recommendation_model import CatalogRecommendation, facts_read
from app.catalog.recommendations import check_catalog, list_recommendations
from app.catalog.texts import MissingValue, fill, placeholders
from app.contracts.causes import CauseId, Recommendation, RetentionSite
from app.contracts.common import Scalar
from app.contracts.report import Limitation, TraceEntry
from app.engine.cause_model import CauseResult
from app.engine.causes import CausesOutcome
from app.engine.rule_conditions import Context, describe_all, evaluate_all, unknown_facts
from app.engine.rule_facts import RuleFacts
from app.engine.source_limitations import TOPICS

IRRIGATION_GROUP = "nawadnianie"
RULE_ID_PREFIX = "recommendation."

# Missing water data are already named by one limitation of the Report; the
# same text is used here, so it is listed once.
_TOPIC_GAP_TEXTS: dict[DataTopic, str] = {"water": TOPICS["hydro"].missing_text}

_NOT_CHECKED = "nie sprawdzano: nie wyznaczono Przyczyn niedoboru"
_NOT_APPLICABLE = "nie dotyczy: nie stwierdzono żadnej z Przyczyn niedoboru, na które odpowiada"
_NOT_MET = "nie uruchomiono: warunek niespełniony"
_IRRIGATION_NOTE = "; treść należy do części Raportu o nawadnianiu"


@dataclass(frozen=True)
class Placed:
    """A triggered recommendation and the found cause it answers."""

    cause: CauseId
    recommendation: Recommendation


@dataclass(frozen=True)
class RulesOutcome:
    # Every triggered recommendation, in the order of the Report.
    placed: tuple[Placed, ...] = ()
    limitations: tuple[Limitation, ...] = ()
    trace: tuple[TraceEntry, ...] = ()

    @property
    def by_cause(self) -> dict[CauseId, list[Recommendation]]:
        """Recommendations of the cause sections; irrigation is not among them."""
        sections: dict[CauseId, list[Recommendation]] = {}
        for item in self.placed:
            if item.recommendation.group != IRRIGATION_GROUP:
                sections.setdefault(item.cause, []).append(item.recommendation)
        return sections

    @property
    def irrigation(self) -> tuple[Placed, ...]:
        """Triggered irrigation entries, for the irrigation part of the Report."""
        return tuple(i for i in self.placed if i.recommendation.group == IRRIGATION_GROUP)


@dataclass(frozen=True)
class _Decision:
    result: str
    values: dict[str, Scalar] = field(default_factory=dict)
    placed: Placed | None = None
    # Why the rule could not be decided: a whole limitation text, or a reason
    # that is completed with the titles of the entries it stopped.
    gaps: tuple[str, ...] = ()


def _quoted(names: Sequence[str]) -> str:
    return ", ".join(f"„{name}”" for name in names)


def _topic_gap(topic: DataTopic) -> str:
    return _TOPIC_GAP_TEXTS.get(topic) or f"brak danych o {TOPIC_LABELS[topic]}"


def _fact_gap(name: str) -> str:
    return f"brak wartości „{FACTS[name].label}”"


def rule_condition(entry: CatalogRecommendation) -> str:
    """The whole rule of an entry in words, for the decision trace."""
    parts = [
        "stwierdzona co najmniej jedna z Przyczyn niedoboru: "
        + _quoted([CAUSE_LABELS[cause] for cause in entry.causes])
    ]
    if entry.requires:
        parts.append("wymagane dane o: " + ", ".join(TOPIC_LABELS[t] for t in entry.requires))
    if entry.conditions:
        parts.append(describe_all(entry.conditions))
    return "; ".join(parts)


def _texts(entry: CatalogRecommendation, context: Context) -> tuple[list[str], str]:
    """Templates of the text (with the additions that apply) and of the gain."""
    text = [entry.text]
    for addition in entry.additions:
        if evaluate_all(addition.conditions, context) is True:
            text.append(addition.text)
    return text, entry.gain


def _decide(
    entry: CatalogRecommendation,
    causes: CausesOutcome,
    facts: RuleFacts,
    fired: set[str],
    sites: Mapping[SiteKind, RetentionSite],
) -> _Decision:
    if causes.status != "determined":
        return _Decision(_NOT_CHECKED)
    answered: CauseResult | None = next(
        (result for result in causes.found if result.id in entry.causes), None
    )
    if answered is None:
        return _Decision(_NOT_APPLICABLE)
    values: dict[str, Scalar] = {
        "cause": answered.id,
        "cause_value": answered.value,
        "cause_threshold": answered.threshold,
    }
    missing = [topic for topic in entry.requires if topic not in facts.available]
    if missing:
        labels = ", ".join(TOPIC_LABELS[topic] for topic in missing)
        gaps = tuple(_topic_gap(topic) for topic in missing)
        return _Decision(f"nie uruchomiono: brak danych o {labels}", values, gaps=gaps)
    context = Context(facts, {result.id for result in causes.found}, fired)
    for condition in entry.conditions:
        values |= {name: facts.get(name) for name in facts_read(condition)}
    holds = evaluate_all(entry.conditions, context)
    if holds is False:
        return _Decision(_NOT_MET, values)
    unknown = list(unknown_facts(entry.conditions, context)) if holds is None else []
    text_templates, gain_template = _texts(entry, context)
    if not unknown:
        try:
            text = " ".join(fill(template, facts.values) for template in text_templates)
            gain = fill(gain_template, facts.values)
        except MissingValue as gap:
            unknown = [gap.name]
    if unknown:
        labels = ", ".join(FACTS[name].label for name in unknown)
        gaps = tuple(_fact_gap(name) for name in unknown)
        return _Decision(f"nie uruchomiono: brak wartości ({labels})", values, gaps=gaps)
    for template in (*text_templates, gain_template):
        values |= {name: facts.get(name) for name in placeholders(template)}
    rule = f"Stwierdzono Przyczynę niedoboru „{CAUSE_LABELS[answered.id]}”"
    if entry.conditions:
        rule += "; " + describe_all(entry.conditions)
    recommendation = Recommendation(
        id=entry.id,
        group=entry.group,
        text=text,
        gain=gain,
        rule=rule + ".",
        inputs=values,
        citation=entry.citation,
        retention_site=sites.get(entry.retention_site) if entry.retention_site else None,
        link=entry.link,
    )
    result = f"uruchomiono w odpowiedzi na Przyczynę niedoboru „{CAUSE_LABELS[answered.id]}”"
    if entry.group == IRRIGATION_GROUP:
        result += _IRRIGATION_NOTE
    return _Decision(result, values, placed=Placed(answered.id, recommendation))


def _limitations(gaps: Mapping[str, list[str]]) -> tuple[Limitation, ...]:
    fixed = set(_TOPIC_GAP_TEXTS.values())
    return tuple(
        Limitation(
            text=gap if gap in fixed else f"Nie sprawdzono Rekomendacji {_quoted(titles)}: {gap}.",
            affects="recommendations",
            permanent=False,
        )
        for gap, titles in gaps.items()
    )


def recommend(
    causes: CausesOutcome,
    facts: RuleFacts,
    catalog: Sequence[CatalogRecommendation] | None = None,
    sites: Mapping[SiteKind, RetentionSite] | None = None,
) -> RulesOutcome:
    """Recommendations for the found causes; `catalog` defaults to the closed catalogue.

    `sites` gives the geometry of the water retention sites that could be
    derived for the parcel, by kind; an entry gets its site only from there.
    """
    entries = list_recommendations() if catalog is None else check_catalog(catalog)
    cause_rank = {result.id: rank for rank, result in enumerate(causes.found)}
    fired: set[str] = set()
    ranked: list[tuple[tuple[int, int, int, int], Placed]] = []
    gaps: dict[str, list[str]] = {}
    trace: list[TraceEntry] = []
    for index, entry in enumerate(entries):
        decision = _decide(entry, causes, facts, fired, sites or {})
        rule_id, condition = RULE_ID_PREFIX + entry.id, rule_condition(entry)
        trace.append(
            TraceEntry(
                rule_id=rule_id, condition=condition, values=decision.values, result=decision.result
            )
        )
        for gap in decision.gaps:
            gaps.setdefault(gap, []).append(entry.title)
        if decision.placed is not None:
            fired.add(entry.id)
            last = entry.group == IRRIGATION_GROUP
            key = (last, cause_rank[decision.placed.cause], GROUP_ORDER.index(entry.group), index)
            ranked.append((key, decision.placed))
    ranked.sort(key=lambda item: item[0])
    return RulesOutcome(
        placed=tuple(placed for _, placed in ranked),
        limitations=_limitations(gaps),
        trace=tuple(trace),
    )
