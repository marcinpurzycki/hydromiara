"""Check of the language model's answer against the Report selection it was given.

Pure. An answer is accepted only when every rule below holds; otherwise the
template is used. What is checked:
- length and plain-prose form;
- every number, date, month name and "X z Y lat" pair occurs in the selection
  (see `numbers` for the notations treated as equal), and a number keeps its unit;
- degrees of the deficit scale, recommendation groups, consistency results and
  advice words occur in the answer only if they occur in the selection;
- a confidence level named next to "pewność" is one the Report gives;
- words the project glossary tells to avoid are absent unless the Report text
  itself uses them; "susza" appears only inside fixed phrases of the Report;
- when no verdict has a deficit level, the answer says so and names no degree.

What this cannot detect: a number moved to another meaning, a number written
in words, a wrong sign, an invented action phrased without any guarded word,
or a wrong emphasis. Those risks are limited by the instruction, by the short
form and by the small selection, not by this check.
"""

import re

from app.summary import params
from app.summary.facts import SummaryFacts
from app.summary.numbers import numbers_problem, read_numbers

_FLAGS = re.IGNORECASE
_AVOIDED = [re.compile(stem, _FLAGS) for stem in params.AVOIDED_STEMS]
_GUARDED = [re.compile(term, _FLAGS) for term in params.GUARDED_TERMS]
# The first four guarded terms are the degrees of the deficit scale.
_DEGREES = _GUARDED[:4]
_DROUGHT = re.compile(params.DROUGHT_STEM, _FLAGS)
_DROUGHT_PHRASES = re.compile("|".join(params.DROUGHT_PHRASES), _FLAGS)
_CONFIDENCE = [re.compile(pattern, _FLAGS) for pattern in params.CONFIDENCE_PATTERNS]
_NOT_ASSESSED = re.compile(params.NOT_ASSESSED_PATTERN, _FLAGS)
_LEVEL_STEMS = {"wysoka": "wysok", "średnia": "średni", "niska": "nisk"}
_QUOTES = "\"'„”“"


def clean_answer(text: str) -> str:
    """One paragraph without surrounding whitespace or quotation marks."""
    cleaned = " ".join(text.split())
    if len(cleaned) >= 2 and cleaned[0] in _QUOTES and cleaned[-1] in _QUOTES:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _confidence_levels(facts: SummaryFacts) -> set[str]:
    levels = set()
    for key in ("biezaca_sytuacja_wodna", "podatnosc_wieloletnia"):
        level = facts.payload.get(key, {}).get("pewnosc_oceny")
        if level in _LEVEL_STEMS:
            levels.add(_LEVEL_STEMS[level])
    return levels


def _wording_problem(answer: str, facts: SummaryFacts) -> str | None:
    source = facts.text
    if _DROUGHT.search(_DROUGHT_PHRASES.sub(" ", answer)):
        return "drought_word"
    for stem in _AVOIDED:
        if stem.search(answer) and not stem.search(source):
            return "avoided_word"
    for term in _GUARDED:
        if term.search(answer) and not term.search(source):
            return "term_not_in_report"
    named = {m.group(1).lower() for pattern in _CONFIDENCE for m in pattern.finditer(answer)}
    if not named <= _confidence_levels(facts):
        return "confidence_changed"
    if not facts.any_assessed:
        if not _NOT_ASSESSED.search(answer):
            return "not_assessed_unsaid"
        if any(degree.search(answer) for degree in _DEGREES):
            return "level_without_assessment"
    return None


def answer_problem(answer: str, facts: SummaryFacts) -> str | None:
    """Code of the first rule the cleaned answer breaks; None when it is accepted."""
    if not answer:
        return "answer_empty"
    if len(answer) > params.MAX_ANSWER_CHARS:
        return "answer_too_long"
    if len(answer) < params.MIN_ANSWER_CHARS:
        return "answer_too_short"
    if any(char in answer for char in params.FORMAT_CHARS) or "http" in answer.lower():
        return "answer_format"
    return (
        numbers_problem(read_numbers(answer), read_numbers(facts.text))
        or _wording_problem(answer, facts)
    )
