"""Deciding and wording the conditions of a recommendation rule.

A condition has three outcomes: it holds, it does not hold, or it cannot be
decided because a fact it reads is unknown (None). "Unknown" is kept apart
from "does not hold" on purpose: a rule that cannot be decided leaves a
limitation in the Report, a rule that is not met leaves only its trace.

Pure: the same condition and context always give the same outcome.
"""

import operator
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from app.catalog.recommendation_facts import CAUSE_LABELS, FACTS
from app.catalog.recommendation_model import (
    ORDERING,
    AllOf,
    AnyOf,
    CauseFound,
    Compare,
    Condition,
    Fired,
    Known,
)
from app.catalog.texts import polish
from app.contracts.causes import CauseId
from app.contracts.common import Scalar
from app.engine.rule_facts import RuleFacts

_OPERATORS = {
    "lt": operator.lt, "le": operator.le, "gt": operator.gt,
    "ge": operator.ge, "eq": operator.eq, "ne": operator.ne,
}  # fmt: skip
_OPERATOR_WORDS = {
    "lt": "poniżej", "le": "najwyżej", "gt": "powyżej",
    "ge": "co najmniej", "eq": "równe", "ne": "inne niż",
}  # fmt: skip


@dataclass(frozen=True)
class Context:
    """What the conditions of one entry are decided against."""

    facts: RuleFacts
    found_causes: Collection[CauseId]
    # Identifiers of the entries triggered earlier in catalogue order.
    fired: Collection[str]


def _is_number(value: Scalar) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _compare(condition: Compare, value: Scalar) -> bool | None:
    if value is None:
        return None
    threshold = condition.value.value
    if condition.op in ORDERING and not _is_number(value):
        return None
    return bool(_OPERATORS[condition.op](value, threshold))


def _combine(outcomes: Sequence[bool | None], *, decisive: bool) -> bool | None:
    """`decisive` settles the result at once: True for any-of, False for all-of."""
    if decisive in outcomes:
        return decisive
    return None if None in outcomes else not decisive


def evaluate(condition: Condition, context: Context) -> bool | None:
    """True or False; None when a fact the condition needs is unknown."""
    if isinstance(condition, Compare):
        return _compare(condition, context.facts.get(condition.fact))
    if isinstance(condition, Known):
        return context.facts.get(condition.fact) is not None
    if isinstance(condition, CauseFound):
        return condition.cause in context.found_causes
    if isinstance(condition, Fired):
        return any(entry in context.fired for entry in condition.entries)
    outcomes = [evaluate(part, context) for part in condition.conditions]
    return _combine(outcomes, decisive=isinstance(condition, AnyOf))


def evaluate_all(conditions: Sequence[Condition], context: Context) -> bool | None:
    """All conditions together; an empty list holds."""
    return _combine([evaluate(part, context) for part in conditions], decisive=False)


def unknown_facts(conditions: Sequence[Condition], context: Context) -> tuple[str, ...]:
    """Facts without a value read by the conditions that could not be decided."""
    names: list[str] = []
    for condition in conditions:
        if evaluate(condition, context) is not None:
            continue
        if isinstance(condition, (AnyOf, AllOf)):
            names += unknown_facts(condition.conditions, context)
        elif isinstance(condition, Compare):
            names.append(condition.fact)
    return tuple(dict.fromkeys(names))


def describe(condition: Condition) -> str:
    """The condition in plain Polish, for the rule shown with a recommendation."""
    if isinstance(condition, Compare):
        if condition.wording:
            return condition.wording
        word = _OPERATOR_WORDS[condition.op]
        return f"{FACTS[condition.fact].label}: {word} {polish(condition.value.value)}"
    if isinstance(condition, Known):
        return condition.wording or f"znana wartość: {FACTS[condition.fact].label}"
    if isinstance(condition, CauseFound):
        return f"stwierdzono Przyczynę niedoboru „{CAUSE_LABELS[condition.cause]}”"
    if isinstance(condition, Fired):
        return "uruchomiono Rekomendację: " + " lub ".join(condition.entries)
    joiner = " lub " if isinstance(condition, AnyOf) else " oraz "
    return "(" + joiner.join(describe(part) for part in condition.conditions) + ")"


def describe_all(conditions: Sequence[Condition]) -> str:
    return "; ".join(describe(part) for part in conditions)
