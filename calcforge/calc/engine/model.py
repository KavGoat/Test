"""The structural expression model the equation editor edits.

SMath does not edit text: it edits a tree.  Typing ``/`` takes the operand to
the left of the cursor into a numerator and moves into a new denominator,
``^`` opens an exponent, ``(`` opens a bracket, and so on.  The model mirrors
that: a :class:`Row` is a sequence of *items*; an item is either a one
character token (``"x"``, ``"2"``, ``"+"``...) or a :class:`Box` holding
child rows (a fraction has two, a power one, a matrix r·c...).

Rows are parsed into an AST (:mod:`websmath.engine.ast`) whenever the
expression is evaluated or drawn, so the model stays close to what the user
typed while the evaluator works on a proper tree.
"""
from __future__ import annotations

from typing import Iterator, Optional, Union

# Characters that form identifiers (with the literal-subscript dot).
GREEK = "αβγδεζηθϑικλμνξοπρσςτυφϕχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"
LETTERS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_" + GREEK + "°¤∞%‰'\"Ω$#")
DIGITS = set("0123456789")

# Operator tokens stored in rows.  "≔" is SMath's definition (typed ':'),
# "=" the evaluation sign, "≡" boolean equality (Ctrl+=).
BINARY = {"+", "-", "*", "<", ">", "≤", "≥", "≠", "≡", "∧", "∨", "⊕", "≔", "=", "×", "←"}
SEPARATORS = {",", ";"}
POSTFIX = {"!"}


class Box:
    """A structural item with child rows."""

    kind = "box"

    def __init__(self, *rows: "Row"):
        self.rows: list[Row] = list(rows)
        for r in self.rows:
            r.parent = self

    def copy(self) -> "Box":
        new = object.__new__(type(self))
        new.__dict__.update(self.__dict__)
        new.rows = [r.copy() for r in self.rows]
        for r in new.rows:
            r.parent = new
        return new

    def __repr__(self) -> str:
        return f"{type(self).__name__}({', '.join(map(repr, self.rows))})"


class Frac(Box):
    kind = "frac"  # rows: numerator, denominator


class Pow(Box):
    kind = "pow"  # rows: exponent (applies to the operand on its left)


class Index(Box):
    kind = "index"  # rows: index expression (v[1 -> v with subscript 1)


class Sqrt(Box):
    kind = "sqrt"  # rows: radicand


class Root(Box):
    kind = "root"  # rows: degree, radicand


class Paren(Box):
    kind = "paren"  # rows: contents; separators ',' split function args


class Abs(Box):
    kind = "abs"


class Matrix(Box):
    kind = "matrix"

    def __init__(self, nrows: int, ncols: int, cells: Optional[list["Row"]] = None):
        cells = cells or [Row() for _ in range(nrows * ncols)]
        super().__init__(*cells)
        self.nrows, self.ncols = nrows, ncols

    def cell(self, i: int, j: int) -> "Row":
        return self.rows[i * self.ncols + j]


class Program(Box):
    """Programming constructs drawn as blocks: if / for / while / line.

    ``name`` selects the layout; rows are the argument slots.  ``line``
    (the multi-line bracket) has a variable number of rows.
    """

    kind = "program"

    def __init__(self, name: str, *rows: "Row"):
        super().__init__(*rows)
        self.name = name


Item = Union[str, Box]


class Row:
    def __init__(self, items: Optional[list[Item]] = None, parent: Optional[Box] = None):
        self.items: list[Item] = []
        self.parent = parent
        for it in items or []:
            self.append(it)

    # -- basic list behaviour -------------------------------------------------
    def append(self, item: Item) -> None:
        self.insert(len(self.items), item)

    def insert(self, index: int, item: Item) -> None:
        if isinstance(item, Box):
            item.parent_row = self
        self.items.insert(index, item)

    def pop(self, index: int) -> Item:
        return self.items.pop(index)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[Item]:
        return iter(self.items)

    def __getitem__(self, i):
        return self.items[i]

    def is_empty(self) -> bool:
        return not self.items

    def copy(self) -> "Row":
        return Row([it.copy() if isinstance(it, Box) else it for it in self.items])

    def text(self) -> str:
        """Linear text form, used by tests and the clipboard."""
        return to_text(self)

    def __repr__(self) -> str:
        return f"Row({self.text()!r})"


def row(text: str) -> Row:
    """Build a row from linear text (tests and file import helper)."""
    from .linear import parse_linear

    return parse_linear(text)


# ---------------------------------------------------------------------------
# Linear text form
# ---------------------------------------------------------------------------

def to_text(r: Row) -> str:
    out = []
    for it in r.items:
        if isinstance(it, str):
            out.append(it)
        else:
            out.append(box_text(it))
    return "".join(out)


def box_text(b: Box) -> str:
    t = [to_text(x) for x in b.rows]
    if isinstance(b, Frac):
        return f"({t[0]})/({t[1]})"
    if isinstance(b, Pow):
        return f"^({t[0]})"
    if isinstance(b, Index):
        return f"[{t[0]}]"
    if isinstance(b, Sqrt):
        return f"√({t[0]})"
    if isinstance(b, Root):
        return f"nthroot({t[0]},{t[1]})"
    if isinstance(b, Paren):
        return f"({t[0]})"
    if isinstance(b, Abs):
        return f"|{t[0]}|"
    if isinstance(b, Matrix):
        return f"mat({','.join(t)},{b.nrows},{b.ncols})"
    if isinstance(b, Program):
        return f"{b.name}{{{';'.join(t)}}}"
    return "?"


def walk_rows(r: Row) -> Iterator[Row]:
    yield r
    for it in r.items:
        if isinstance(it, Box):
            for c in it.rows:
                yield from walk_rows(c)
