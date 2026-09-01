"""Collecting everything in a document that did not evaluate.

Because reading order decides what is defined, moving a region can legitimately
break something further down the page.  The list this module builds is how that
shows up as a warning rather than as a silently wrong sheet.
"""
from __future__ import annotations

from dataclasses import dataclass

UNDEFINED = "undefined"
UNIT_MISMATCH = "units"
SYNTAX = "syntax"
OTHER = "error"

LABELS = {
    UNDEFINED: "Undefined name",
    UNIT_MISMATCH: "Unit mismatch",
    SYNTAX: "Syntax",
    OTHER: "Error",
}


@dataclass
class Problem:
    """One thing that did not evaluate, and where to find it."""

    page: int                  # zero-based
    item_uid: str
    where: str                 # "line 3" or "cell C7"
    kind: str
    message: str
    source: str = ""
    item_name: str = ""

    @property
    def label(self) -> str:
        return LABELS.get(self.kind, LABELS[OTHER])


def classify(message: str) -> str:
    lowered = message.lower()
    if "not defined" in lowered or "unknown unit or name" in lowered:
        return UNDEFINED
    if "units do not match" in lowered or "dimensionality" in lowered:
        return UNIT_MISMATCH
    if "syntax" in lowered:
        return SYNTAX
    return OTHER


def collect_problems(document) -> list[Problem]:
    """Every unevaluated statement and failed cell, in reading order."""
    from ..items.mathitem import MathItem
    from ..items.tableitem import TableItem
    from ..core.spreadsheet import column_letter

    problems: list[Problem] = []
    for index, page in enumerate(document.pages):
        if page.scene is None:
            continue
        for item in page.scene.ordered_markups():
            if isinstance(item, MathItem):
                for line, statement in enumerate(item.statements, start=1):
                    if statement.error:
                        problems.append(Problem(
                            page=index, item_uid=item.uid,
                            where=f"line {line}" if len(item.statements) > 1 else "",
                            kind=classify(statement.error), message=statement.error,
                            source=statement.raw.strip(), item_name=item.display_name()))
            elif isinstance(item, TableItem):
                for (row, col), cell in sorted(item.sheet.cells.items()):
                    if cell.error:
                        problems.append(Problem(
                            page=index, item_uid=item.uid,
                            where=f"cell {column_letter(col)}{row + 1}",
                            kind=classify(cell.error), message=cell.error,
                            source=cell.raw, item_name=item.display_name()))
    return problems


def summarise(problems: list[Problem]) -> str:
    """A short status-bar line, e.g. '2 undefined · 1 unit mismatch'."""
    if not problems:
        return ""
    counts: dict[str, int] = {}
    for problem in problems:
        counts[problem.kind] = counts.get(problem.kind, 0) + 1
    order = [UNDEFINED, UNIT_MISMATCH, SYNTAX, OTHER]
    parts = [f"{counts[kind]} {LABELS[kind].lower()}" for kind in order if kind in counts]
    return " · ".join(parts)
