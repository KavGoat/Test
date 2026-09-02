"""An independent second opinion on a document's numbers.

The evaluation pass that fills the page in is fast and incremental: it reuses
what it can, it evaluates in reading order, and it stops at the first error on
a line.  That is the right behaviour for typing into, and the wrong behaviour
for trusting.

This module re-derives the whole document from its source text in a clean
workspace and compares the answers with what is on the page.  Anything it
cannot confirm is reported.  It shares no state with the live workspace, so a
stale value, a cached result, or a definition that has quietly gone missing
shows up as a disagreement rather than as a number nobody questions.

It also carries the sanity checks that are cheap to state and worth stating: a
name that shadows a unit, a name defined twice, a result whose dimension does
not match its own target unit, and a magnitude far outside anything a building
is made of.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from .engine import Workspace, evaluate_source
from .problems import Problem
from .units import Quantity, format_quantity

# Problem kinds this module raises, on top of the ones the live pass raises.
DISAGREEMENT = "disagreement"
SHADOWED = "shadowed"
REDEFINED = "redefined"
IMPLAUSIBLE = "implausible"

VERIFY_LABELS = {
    DISAGREEMENT: "Does not re-derive",
    SHADOWED: "Shadows a unit",
    REDEFINED: "Defined twice",
    IMPLAUSIBLE: "Implausible magnitude",
}

# How far two answers may differ and still count as the same number.  This is
# floating-point noise, not engineering tolerance: anything larger is a real
# disagreement and is reported.
TOLERANCE = 1e-9

# Magnitudes outside these bands are almost certainly a slip — a stress in
# exapascals, a beam a thousand kilometres long.  Reported as a question, never
# as an error, because unusual is not the same as wrong.
PLAUSIBLE = [
    ({"[length]": 1}, 1e-6, 1e5, "m"),                       # 1 µm .. 100 km
    ({"[mass]": 1, "[length]": 1, "[time]": -2}, 1e-3, 1e10, "N"),
    ({"[mass]": 1, "[length]": -1, "[time]": -2}, 1e-3, 1e13, "Pa"),
    ({"[mass]": 1, "[length]": 2, "[time]": -2}, 1e-3, 1e10, "N*m"),
]


@dataclass
class Verification:
    """What the check found, and how much of the document it covered."""

    problems: list[Problem]
    statements: int = 0
    cells: int = 0
    confirmed: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        checked = self.statements + self.cells
        if not checked:
            return "Nothing to check yet"
        if self.ok:
            return (f"Re-derived {self.confirmed} of {checked} values — "
                    "every one agreed")
        return (f"Re-derived {self.confirmed} of {checked} values — "
                f"{len(self.problems)} to look at")


def verify_document(document) -> Verification:
    """Re-derive every calculation in *document* and report the differences."""
    from ..items.mathitem import MathItem
    from ..items.tableitem import TableItem
    from .spreadsheet import column_letter

    problems: list[Problem] = []
    statements = cells = confirmed = 0

    # A workspace of its own, built from nothing.
    fresh = Workspace()
    fresh.declare(_document_names(document))
    fresh.begin_pass()

    defined_at: dict[str, str] = {}

    for index, page in enumerate(document.pages):
        if page.scene is None:
            continue
        for item in page.scene.ordered_markups():
            where = f"{item.display_name()}"
            if isinstance(item, MathItem):
                target = fresh.child() if item.scoped else fresh
                rederived = evaluate_source(item.source, target,
                                            item.label or "Calculation",
                                            new_pass=False)
                for line, (before, after) in enumerate(
                        zip(item.statements, rederived), start=1):
                    statements += 1
                    place = f"line {line}" if len(item.statements) > 1 else ""
                    problem = _compare(before, after, index, item, place)
                    if problem is not None:
                        problems.append(problem)
                    else:
                        confirmed += 1
                    problems.extend(_inspect(after, index, item, place,
                                             defined_at, where))
            elif isinstance(item, TableItem):
                for (row, col), cell in sorted(item.sheet.cells.items()):
                    if cell.raw:
                        cells += 1
                        confirmed += 0 if cell.error else 1
                item.refresh(fresh)
                for name in item.declared_names():
                    _note_definition(name, f"{where} cell", defined_at,
                                     problems, index, item, "")
    return Verification(problems=problems, statements=statements,
                        cells=cells, confirmed=confirmed)


def _document_names(document) -> set[str]:
    names: set[str] = set()
    for page in document.pages:
        if page.scene is None:
            continue
        for item in page.scene.ordered_markups():
            declared = getattr(item, "declared_names", None)
            if callable(declared):
                names |= declared()
    return names


def _compare(before, after, page: int, item, place: str) -> Optional[Problem]:
    """Report when the re-derived answer is not the one on the page."""
    if before.error or after.error:
        # Errors are already reported by the live pass; only a *new* error
        # matters here, and that is a disagreement about whether it works.
        if bool(before.error) == bool(after.error):
            return None
        message = (f"re-deriving this gives “{after.error}”" if after.error
                   else "this only works on the second pass")
        return _problem(page, item, place, DISAGREEMENT, message, before)
    if _same(before.result, after.result):
        return None
    return _problem(
        page, item, place, DISAGREEMENT,
        f"the page shows {format_quantity(before.result, 6)}, "
        f"re-deriving gives {format_quantity(after.result, 6)}", before)


def _inspect(statement, page: int, item, place: str, defined_at: dict,
             where: str) -> list[Problem]:
    """The cheap sanity checks that are worth making on every definition."""
    found: list[Problem] = []
    if statement.error or not statement.name:
        return found
    _note_definition(statement.name, where, defined_at, found, page, item, place)

    target = statement.target_unit
    if target and isinstance(statement.result, Quantity):
        try:
            statement.result.to(target)
        except Exception:
            found.append(_problem(
                page, item, place, DISAGREEMENT,
                f"the result cannot be shown in {target}", statement))

    doubt = _implausible(statement.result)
    if doubt:
        found.append(_problem(page, item, place, IMPLAUSIBLE, doubt, statement))
    return found


def _note_definition(name: str, where: str, defined_at: dict,
                     found: list, page: int, item, place: str) -> None:
    if name in defined_at and defined_at[name] != where:
        found.append(_problem(
            page, item, place, REDEFINED,
            f"“{name}” is also defined in {defined_at[name]} — "
            "the later one wins, in reading order", None))
    elif _shadows_a_unit(name):
        found.append(_problem(
            page, item, place, SHADOWED,
            f"“{name}” is also the name of a unit, so writing it after a "
            "number in this document no longer means that unit", None))
    defined_at.setdefault(name, where)


def _shadows_a_unit(name: str) -> bool:
    """True for a name that would stop a real unit from meaning what it says.

    Single letters are excluded: L is a span, M is a moment, A is an area and
    V is a shear on every calculation sheet ever written, and warning about
    litres, molar, amperes and volts would be nothing but noise. A name that
    spells out a unit in full — kg, mm, psi — is worth a word, because writing
    "2 kg" further down the page will then mean something else.
    """
    from .units import is_unit_name

    return len(name) > 1 and name.isalpha() and is_unit_name(name)


def _implausible(value: Any) -> str:
    """A magnitude worth a second look, or an empty string."""
    if not isinstance(value, Quantity):
        return ""
    try:
        magnitude = abs(float(value.to_base_units().magnitude))
    except Exception:
        return ""
    if magnitude == 0 or not math.isfinite(magnitude):
        return ""
    dimension = {str(k): int(v) for k, v in value.dimensionality.items()}
    for candidate, low, high, unit in PLAUSIBLE:
        if dimension != candidate:
            continue
        if magnitude < low:
            return f"this is very small for a {unit} — check the units"
        if magnitude > high:
            return f"this is very large for a {unit} — check the units"
    return ""


def _same(first: Any, second: Any) -> bool:
    """True when two answers are the same number in the same dimension."""
    if isinstance(first, Quantity) != isinstance(second, Quantity):
        return False
    try:
        if isinstance(first, Quantity):
            if first.dimensionality != second.dimensionality:
                return False
            a = float(first.to_base_units().magnitude)
            b = float(second.to_base_units().magnitude)
        elif isinstance(first, bool) or isinstance(second, bool):
            return bool(first) is bool(second)
        elif isinstance(first, (int, float)) and isinstance(second, (int, float)):
            a, b = float(first), float(second)
        else:
            return repr(first) == repr(second)
    except Exception:
        return repr(first) == repr(second)
    if math.isnan(a) and math.isnan(b):
        return True
    if a == b:
        return True
    scale = max(abs(a), abs(b), 1e-300)
    return abs(a - b) / scale <= TOLERANCE


def _problem(page: int, item, place: str, kind: str, message: str,
             statement) -> Problem:
    return Problem(page=page, item_uid=item.uid, where=place, kind=kind,
                   message=message,
                   source=statement.raw.strip() if statement is not None else "",
                   item_name=item.display_name())
