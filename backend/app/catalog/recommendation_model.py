"""Model of a recommendation catalogue entry and of the conditions of its rule.

An entry answers one or more deficit causes and is considered only when at
least one of them is found. Its rule is written as data: the data topics it
requires and a list of conditions, all of which must hold. Conditions come
from a small closed set of kinds, so adding an entry never adds code:

- `compare`      a parcel fact against a threshold that carries its provenance,
- `known`        a parcel fact has a value (e.g. the terrain shows a lowest part),
- `cause_found`  a named deficit cause is found,
- `fired`        one of the named earlier entries was triggered,
- `any_of`, `all_of`  combinations of the above.

Texts are templates filled with parcel facts. An entry never states sizes,
costs or parameters of a structure.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.catalog.crop_model import CatalogModel, Sourced
from app.catalog.recommendation_facts import FACTS, RETENTION_GROUPS, DataTopic, SiteKind
from app.catalog.texts import placeholders
from app.contracts.causes import CauseId, RecommendationGroup

Operator = Literal["lt", "le", "gt", "ge", "eq", "ne"]
ORDERING: frozenset[str] = frozenset({"lt", "le", "gt", "ge"})
Threshold = bool | int | float | str


def _known_fact(name: str) -> str:
    if name not in FACTS:
        raise ValueError(f"unknown parcel fact: {name!r}")
    return name


class Compare(CatalogModel):
    kind: Literal["compare"] = "compare"
    fact: str
    op: Operator
    # The threshold with its source, or the reason why it is a working value.
    value: Sourced[Threshold]
    # The condition in plain Polish; generated from the fact name when None.
    wording: str | None = None

    @model_validator(mode="after")
    def _is_comparable(self) -> Self:
        _known_fact(self.fact)
        threshold = self.value.value
        numeric = isinstance(threshold, (int, float)) and not isinstance(threshold, bool)
        if self.op in ORDERING and not numeric:
            raise ValueError("an ordering comparison needs a numeric threshold")
        return self


class Known(CatalogModel):
    kind: Literal["known"] = "known"
    fact: str
    wording: str | None = None

    @model_validator(mode="after")
    def _names_a_fact(self) -> Self:
        _known_fact(self.fact)
        return self


class CauseFound(CatalogModel):
    kind: Literal["cause_found"] = "cause_found"
    cause: CauseId


class Fired(CatalogModel):
    """True when at least one of the named entries, listed earlier, was triggered."""

    kind: Literal["fired"] = "fired"
    entries: tuple[str, ...] = Field(min_length=1)


class AnyOf(CatalogModel):
    kind: Literal["any_of"] = "any_of"
    conditions: tuple["Condition", ...] = Field(min_length=1)


class AllOf(CatalogModel):
    kind: Literal["all_of"] = "all_of"
    conditions: tuple["Condition", ...] = Field(min_length=1)


Condition = Annotated[
    Compare | Known | CauseFound | Fired | AnyOf | AllOf, Field(discriminator="kind")
]
AnyOf.model_rebuild()
AllOf.model_rebuild()


def facts_read(condition: Condition) -> tuple[str, ...]:
    """Names of the parcel facts a condition reads, in order, without repeats."""
    if isinstance(condition, (Compare, Known)):
        return (condition.fact,)
    if isinstance(condition, (AnyOf, AllOf)):
        names = [name for part in condition.conditions for name in facts_read(part)]
        return tuple(dict.fromkeys(names))
    return ()


def entries_read(condition: Condition) -> tuple[str, ...]:
    """Identifiers of the other entries a condition refers to."""
    if isinstance(condition, Fired):
        return condition.entries
    if isinstance(condition, (AnyOf, AllOf)):
        return tuple(name for part in condition.conditions for name in entries_read(part))
    return ()


class Addition(CatalogModel):
    """A sentence added to the text of an entry when its conditions hold."""

    text: str = Field(min_length=1)
    conditions: tuple[Condition, ...] = ()


class CatalogRecommendation(CatalogModel):
    """One position of the closed recommendation catalogue."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    # Short name, used when the Report says that the entry could not be checked.
    title: str = Field(min_length=1)
    group: RecommendationGroup
    # Deficit causes the entry answers; one found cause is enough.
    causes: tuple[CauseId, ...] = Field(min_length=1)
    # Data topics the rule needs beyond the cause; without them it is not run.
    requires: tuple[DataTopic, ...] = ()
    # All must hold. Empty: the found cause alone triggers the entry.
    conditions: tuple[Condition, ...] = ()
    text: str = Field(min_length=1)
    additions: tuple[Addition, ...] = ()
    # Template of the column "Co uzyskasz".
    gain: str = Field(min_length=1)
    # The source shown in the Report: what the content really rests on.
    citation: str = Field(min_length=1)
    # Why the content or its citation is still a working one; None when final.
    provisional: str | None = None
    retention_site: SiteKind | None = None
    link: str | None = None

    @property
    def is_provisional(self) -> bool:
        return self.provisional is not None

    def templates(self) -> tuple[str, ...]:
        return (self.text, self.gain, *(addition.text for addition in self.additions))

    def all_conditions(self) -> tuple[Condition, ...]:
        extra = [part for addition in self.additions for part in addition.conditions]
        return (*self.conditions, *extra)

    def facts_used(self) -> tuple[str, ...]:
        """Every parcel fact the entry reads: in its conditions and in its texts."""
        names = [name for part in self.all_conditions() for name in facts_read(part)]
        names += [name for template in self.templates() for name in placeholders(template)]
        return tuple(dict.fromkeys(names))

    @model_validator(mode="after")
    def _is_consistent(self) -> Self:
        if len(set(self.causes)) != len(self.causes):
            raise ValueError("a cause is listed twice")
        if len(set(self.requires)) != len(self.requires):
            raise ValueError("a required data topic is listed twice")
        for name in self.facts_used():
            topic = FACTS[_known_fact(name)].topic
            if topic not in self.requires:
                raise ValueError(f"fact {name!r} needs the data topic {topic!r} in `requires`")
        if self.provisional is not None and not self.provisional.strip():
            raise ValueError("a provisional mark needs a reason")
        if self.retention_site is not None and self.group not in RETENTION_GROUPS:
            raise ValueError("only retention entries may point to a water retention site")
        if any(self.id in entries_read(part) for part in self.all_conditions()):
            raise ValueError("an entry cannot depend on itself")
        return self
