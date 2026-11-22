"""Text templates of the recommendation catalogue, filled with values of the parcel.

A template is plain Polish text with named places in braces, for example
"Teren Działki opada na {downhill_label}". A place holds the name of a parcel
fact and nothing else: no format specification, no conversion, no expression.
Numbers are written the Polish way (decimal comma).

Filling never leaves an empty place: a missing or unknown value raises
`MissingValue`, so the caller can skip the recommendation and report the gap.
"""

from collections.abc import Mapping
from string import Formatter

from app.contracts.common import Scalar


class TemplateError(ValueError):
    """The template itself is malformed."""


class MissingValue(LookupError):
    """A place of the template has no value; `name` is the fact that is missing."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def placeholders(template: str) -> tuple[str, ...]:
    """Names of the places of a template, in order of first appearance."""
    names: list[str] = []
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as error:
        raise TemplateError(f"malformed template: {error}") from error
    for _, name, spec, conversion in parsed:
        if name is None:
            continue
        if not name.isidentifier() or spec or conversion:
            raise TemplateError(f"a template place must be a plain fact name, got {name!r}")
        if name not in names:
            names.append(name)
    return tuple(names)


def polish(value: Scalar) -> str:
    """A value as written in a text for the user."""
    if isinstance(value, bool):
        return "tak" if value else "nie"
    if isinstance(value, float):
        whole = value == int(value)
        return str(int(value)) if whole else f"{value:g}".replace(".", ",")
    return str(value)


def fill(template: str, values: Mapping[str, Scalar]) -> str:
    """The template with every place replaced by its value."""
    names = placeholders(template)
    for name in names:
        value = values.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise MissingValue(name)
    return template.format(**{name: polish(values[name]) for name in names})
