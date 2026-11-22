"""Limitations that follow from how the source data were obtained.

Two cases per data category: the data are missing, or they came from a less
accurate substitute further down the substitute chain. Each text names the
conclusion of the Report that is affected.

Pure: reads only the source data and the outcome records stored with them.
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Literal

from app.contracts.report import Limitation
from app.contracts.source_data import SourceData, SourceOutcome, SourceTopic
from app.engine.findings import Finding

Affects = Literal["current", "multiyear", "recommendations", "all"]


@dataclass(frozen=True)
class TopicWording:
    """How one data category is named in limitations."""

    affects: Affects
    # Start of the sentence about a substitute, e.g. "Dane o glebie pochodzą".
    substitute_subject: str
    # The conclusion a substitute affects, completing "Wpływa to na: ...".
    substitute_conclusion: str
    # Full text and short wording used when the category has no data at all;
    # None when the absence is reported elsewhere.
    missing_text: str | None = None
    missing_reason: str | None = None
    # True when the links are services delivering the same data, so a later
    # link is not less accurate and creates no limitation.
    equivalent_links: bool = False


# In the order the limitations are listed in the Report.
TOPICS: dict[SourceTopic, TopicWording] = {
    "weather": TopicWording(
        affects="all",
        substitute_subject="Dane pogodowe pochodzą",
        substitute_conclusion=(
            "oba werdykty: Bieżącą sytuację wodną i Podatność wieloletnią"
        ),
    ),
    "soil": TopicWording(
        affects="all",
        substitute_subject="Dane o glebie pochodzą",
        substitute_conclusion=(
            "oba werdykty, bo od gleby zależy pojemność wodna przyjęta w bilansie wodnym"
        ),
        # Missing soil is reported from the root zone the balance really used.
    ),
    "satellite": TopicWording(
        affects="all",
        substitute_subject="Odczyty satelitarne pochodzą",
        substitute_conclusion="Sprawdzenie zgodności obu werdyktów",
        missing_text=(
            "Brak odczytów satelitarnych dla Działki: werdyktów nie można zestawić "
            "z obrazem roślinności w Sprawdzeniu zgodności."
        ),
        missing_reason="brak odczytów satelitarnych do Sprawdzenia zgodności",
        equivalent_links=True,
    ),
    "drought_background": TopicWording(
        affects="current",
        substitute_subject="Niezależny wskaźnik suszy pochodzi",
        substitute_conclusion="Sprawdzenie zgodności Bieżącej sytuacji wodnej",
        missing_text=(
            "Brak niezależnego wskaźnika suszy dla okresu Daty analizy: Bieżącej sytuacji "
            "wodnej nie można z nim zestawić w Sprawdzeniu zgodności."
        ),
        missing_reason="brak niezależnego wskaźnika suszy do Sprawdzenia zgodności",
    ),
    "terrain": TopicWording(
        affects="recommendations",
        substitute_subject="Dane o ukształtowaniu terenu pochodzą",
        substitute_conclusion=(
            "ocenę, czy woda szybko odpływa z pola, i na wskazanie Miejsc zatrzymania wody"
        ),
        missing_text=(
            "Brak danych o ukształtowaniu terenu: nie można ocenić, czy woda szybko odpływa "
            "z pola, ani wskazać Miejsc zatrzymania wody."
        ),
    ),
    "hydro": TopicWording(
        affects="recommendations",
        substitute_subject="Dane o ciekach, rowach i zbiornikach pochodzą",
        substitute_conclusion="Rekomendacje dotyczące rowów i cieków",
        missing_text=(
            "Brak danych o ciekach, rowach i zbiornikach w otoczeniu Działki: "
            "Rekomendacje dotyczące rowów i cieków nie powstają."
        ),
    ),
}


def step_down_finding(outcome: SourceOutcome) -> Finding | None:
    """The limitation for data that came from a substitute, or None.

    Depends only on the topic, the chain step and the name of the link, so the
    same outcome always gives the same text.
    """
    wording = TOPICS.get(outcome.topic)
    if wording is None or wording.equivalent_links:
        return None
    if not outcome.ok or outcome.chain_step is None or outcome.chain_step <= 1:
        return None
    name = f" ({outcome.source_name})" if outcome.source_name else ""
    text = (
        f"{wording.substitute_subject} z mniej dokładnego zamiennika{name}, bo źródło "
        f"podstawowe nie dało danych. Wpływa to na: {wording.substitute_conclusion}."
    )
    subject = wording.substitute_subject[0].lower() + wording.substitute_subject[1:]
    return Finding(
        limitation=Limitation(text=text, affects=wording.affects, permanent=False),
        reason=f"{subject} z mniej dokładnego zamiennika",
    )


def step_down_limitation(outcome: SourceOutcome) -> Limitation | None:
    finding = step_down_finding(outcome)
    return None if finding is None else finding.limitation


def step_down_findings(outcomes: Iterable[SourceOutcome]) -> list[Finding]:
    """Substitute limitations of all outcomes, in the fixed order of the topics."""
    by_topic: dict[str, Finding] = {}
    for outcome in outcomes:
        finding = step_down_finding(outcome)
        if finding is not None:
            by_topic.setdefault(outcome.topic, finding)
    return [by_topic[topic] for topic in TOPICS if topic in by_topic]


def missing_source_findings(
    source_data: SourceData, skip: Collection[SourceTopic] = ()
) -> list[Finding]:
    """One limitation per data category the analysis ran without.

    It does not matter why the data are absent (the source failed, was too
    slow or is not used): the conclusion that lacks them is the same.
    Categories in `skip` are left out: the caller names their absence itself.
    """
    findings = []
    for topic, wording in TOPICS.items():
        if wording.missing_text is None or getattr(source_data, topic) is not None:
            continue
        if topic in skip:
            continue
        findings.append(
            Finding(
                limitation=Limitation(
                    text=wording.missing_text, affects=wording.affects, permanent=False
                ),
                reason=wording.missing_reason,
            )
        )
    return findings
