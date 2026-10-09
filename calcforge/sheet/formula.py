"""Excel formulas: reading them, and rewriting their references.

A formula is kept as the text the user typed. It is split into tokens that
remember the spaces in front of them, so when a reference has to change
(the formula is copied, rows are inserted, a sheet is renamed) only that
reference's text is rewritten and everything else stays as typed.

To calculate, the tokens are parsed into a tree whose references are kept
relative to the formula's own cell, the way Excel's R1C1 form is: copied
down a column, =A1*2, =A2*2, =A3*2... are one and the same tree, parsed once.

Beyond Excel:
  * a number may carry a unit: =5 kN, =A1 + 250 mm, =10 kN/m*B2
  * 'kN on its own is that unit (SMath's way of writing one): =A1/'kN
  * a bare name that is no cell and no defined name is a variable from the
    document's equations, read where the sheet sits in reading order;
    var(M20) reads a document variable whose name looks like a cell.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Callable, Optional

from .refs import MAX_COLS, MAX_ROWS, CellRef, RangeRef, parse_range, quote_sheet
from .values import ERRORS, is_unit_text


class FormulaError(ValueError):
    """The formula can't be read (Excel: "There's a problem with this formula")."""

    def __init__(self, message: str, pos: int = 0):
        super().__init__(message)
        self.pos = pos


# -- tokens -------------------------------------------------------------------------
@dataclass
class Token:
    kind: str           # num str bool err ref name func unit op ( ) , ; { }
    text: str           # exactly as typed
    lead: str = ""      # the spaces before it
    pos: int = 0
    ref: object = None  # CellRef or RangeRef for "ref"


_SHEET_PREFIX = r"(?:'(?:[^']|'')+'|[A-Za-z_À-￿][\w.À-￿]*)!"
_CELL = r"\$?[A-Za-z]{1,3}\$?[0-9]{1,7}"
_RANGE_RE = re.compile(
    rf"({_SHEET_PREFIX})?(?:({_CELL}):({_CELL})|(\$?[A-Za-z]{{1,3}}):(\$?[A-Za-z]{{1,3}})|(\$?[0-9]{{1,7}}):(\$?[0-9]{{1,7}})|({_CELL}))"
    r"(?![\w.(À-￿!\[])")
_NUMBER_RE = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_NAME_RE = re.compile(r"[A-Za-z_\\À-￿][\w.À-￿]*")
_ERROR_RE = re.compile(r"#(?:DIV/0!|N/A|NAME\?|NULL!|NUM!|REF!|VALUE!|SPILL!|CALC!|UNITS!|GETTING_DATA)", re.I)
_OPS = ("<>", "<=", ">=", "+", "-", "*", "/", "^", "&", "=", "<", ">", "%", ":")


def tokenize(text: str) -> list[Token]:
    """Tokens of a formula without its leading "="."""
    out: list[Token] = []
    i, n = 0, len(text)
    while i < n:
        start = i
        while i < n and text[i] in " \t\r\n":
            i += 1
        lead = text[start:i]
        if i >= n:
            if out:
                out[-1].text += ""      # trailing spaces are kept on a sentinel
            out.append(Token("end", "", lead, i))
            return out
        ch = text[i]
        m = _RANGE_RE.match(text, i)
        if m and (ch.isalpha() or ch in "$'_" or ch.isdigit() or ord(ch) > 127):
            whole = m.group(0)
            # a row range like 3:7 only where a reference can stand
            looks_like_rows = m.group(6) is not None
            if looks_like_rows and out and out[-1].kind in ("num", "ref", "name", ")", "str", "bool", "unit"):
                m = None
            if m:
                ref = parse_range(whole)
                if ref is not None:
                    out.append(Token("ref", whole, lead, i, ref))
                    i = m.end()
                    continue
        if ch == '"':
            j = i + 1
            while True:
                k = text.find('"', j)
                if k < 0:
                    raise FormulaError("A text in the formula has no closing quote.", i)
                if k + 1 < n and text[k + 1] == '"':
                    j = k + 2
                    continue
                break
            out.append(Token("str", text[i:k + 1], lead, i))
            i = k + 1
            continue
        if ch == "#":
            m = _ERROR_RE.match(text, i)
            if not m:
                raise FormulaError("Unknown error value.", i)
            out.append(Token("err", m.group(0).upper(), lead, i))
            i = m.end()
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            m = _NUMBER_RE.match(text, i)
            out.append(Token("num", m.group(0), lead, i))
            i = m.end()
            continue
        if ch == "'":
            # 'Sheet name'!... was taken above as a reference; here it's a unit
            m = _NAME_RE.match(text, i + 1)
            j = i + 1
            if m is None:
                m2 = re.compile(r"[°%µμΩ][\w]*").match(text, i + 1)
                if m2 is None:
                    raise FormulaError("Unknown sheet or unit.", i)
                m = m2
            k = m.end()
            # allow kN/m written after the apostrophe: 'kN/m, 'm^2
            unit_m = re.compile(r"[\w°µμΩ%]+(?:\^-?[0-9.]+)?(?:[*/·][\w°µμΩ%]+(?:\^-?[0-9.]+)?)*").match(text, j)
            if unit_m and is_unit_text(unit_m.group(0)):
                k = unit_m.end()
            unit = text[j:k]
            if not is_unit_text(unit):
                raise FormulaError(f"'{unit} is not a unit.", i)
            out.append(Token("unit", text[i:k], lead, i))
            i = k
            continue
        if ch.isalpha() or ch in "_\\" or ord(ch) > 127 and ch not in "°µμΩ·":
            m = _NAME_RE.match(text, i)
            j = m.end()
            word = m.group(0)
            # Sheet1!Name (a defined name on that sheet)
            if j < n and text[j] == "!":
                m2 = _NAME_RE.match(text, j + 1)
                if not m2:
                    raise FormulaError("A sheet name must be followed by a cell or a name.", i)
                out.append(Token("name", text[i:m2.end()], lead, i))
                i = m2.end()
                continue
            k = j
            while k < n and text[k] == " ":
                k += 1
            if k < n and text[k] == "(":
                out.append(Token("func", word, lead, i))
            elif word.upper() in ("TRUE", "FALSE"):
                out.append(Token("bool", word, lead, i))
            else:
                out.append(Token("name", word, lead, i))
            i = j
            continue
        if ch in "°µμΩ":
            m = re.compile(r"[°µμΩ][\w]*").match(text, i)
            out.append(Token("name", m.group(0), lead, i))
            i = m.end()
            continue
        for op in _OPS:
            if text.startswith(op, i):
                out.append(Token("op", op, lead, i))
                i += len(op)
                break
        else:
            if ch in "(),;{}":
                out.append(Token(ch, ch, lead, i))
                i += 1
            elif ch == "·":
                out.append(Token("op", "*", lead, i))
                out[-1].text = "·"
                i += 1
            else:
                raise FormulaError(f"“{ch}” can't be used here.", i)
    out.append(Token("end", "", "", n))
    return out


def join(tokens: list[Token]) -> str:
    return "".join(t.lead + t.text for t in tokens)


# -- the tree ------------------------------------------------------------------------
# References in the tree are relative to the formula's cell where they have no $:
# Ref.row is then an offset, as in R1C1 notation.
@dataclass(frozen=True)
class Num:
    value: float


@dataclass(frozen=True)
class Str:
    value: str


@dataclass(frozen=True)
class Bool:
    value: bool


@dataclass(frozen=True)
class Err:
    code: str


@dataclass(frozen=True)
class Unit:
    """1 of a unit: 5 kN is Mul(Num 5, Unit kN), written together."""

    text: str


@dataclass(frozen=True)
class Ref:
    row: int
    col: int
    row_abs: bool
    col_abs: bool
    sheet: Optional[str]

    def at(self, row: int, col: int) -> tuple:
        return (self.row if self.row_abs else row + self.row,
                self.col if self.col_abs else col + self.col)


@dataclass(frozen=True)
class Area:
    first: Ref
    last: Ref
    whole: str
    sheet: Optional[str]


@dataclass(frozen=True)
class BadRef:
    """A reference that was deleted or copied off the sheet: #REF!."""


@dataclass(frozen=True)
class Name:
    name: str
    sheet: Optional[str] = None


@dataclass(frozen=True)
class DocVar:
    """var(M20): a document variable whose name looks like a cell."""

    name: str


@dataclass(frozen=True)
class Call:
    name: str           # upper case, _xlfn. removed
    args: tuple


@dataclass(frozen=True)
class Missing:
    """An argument left out: IF(A1,,2)."""


@dataclass(frozen=True)
class Unary:
    op: str
    arg: object


@dataclass(frozen=True)
class Percent:
    arg: object


@dataclass(frozen=True)
class Binary:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class ArrayLit:
    rows: tuple


@dataclass
class Parsed:
    tree: object
    volatile: bool
    names: frozenset            # bare names it reads (defined names or document variables)
    functions: frozenset


VOLATILE = {"NOW", "TODAY", "RAND", "RANDBETWEEN", "RANDARRAY", "OFFSET", "INDIRECT", "CELL", "INFO"}

_PREC = {"=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1, "&": 2, "+": 3, "-": 3, "*": 4, "/": 4, "^": 5}
_LEFT_ASSOC = True  # Excel: 2^3^2 = 64


class _Parser:
    def __init__(self, tokens: list[Token], row: int, col: int):
        self.t = tokens
        self.i = 0
        self.row = row
        self.col = col
        self.names: set = set()
        self.functions: set = set()

    def peek(self, k=0) -> Token:
        return self.t[min(self.i + k, len(self.t) - 1)]

    def take(self) -> Token:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expect(self, kind: str) -> Token:
        tok = self.peek()
        if tok.kind != kind:
            raise FormulaError(f"Expected “{kind}”.", tok.pos)
        return self.take()

    def parse(self):
        if self.peek().kind == "end":
            raise FormulaError("The formula is empty.", 0)
        node = self.expr(0)
        if self.peek().kind != "end":
            raise FormulaError("There's a problem with this formula.", self.peek().pos)
        return node

    def expr(self, min_prec: int):
        left = self.unary()
        while True:
            tok = self.peek()
            if tok.kind != "op" or tok.text not in _PREC:
                break
            prec = _PREC[tok.text]
            if prec < min_prec:
                break
            self.take()
            op = "*" if tok.text == "·" else tok.text
            right = self.expr(prec + 1)
            left = Binary(op, left, right)
        return left

    def unary(self):
        tok = self.peek()
        if tok.kind == "op" and tok.text in ("-", "+"):
            self.take()
            arg = self.unary()
            return Unary(tok.text, arg)
        return self.postfix()

    def postfix(self):
        node = self.ranged()
        while self.peek().kind == "op" and self.peek().text == "%":
            self.take()
            node = Percent(node)
        return node

    def ranged(self):
        node = self.primary()
        while self.peek().kind == "op" and self.peek().text == ":":
            self.take()
            right = self.primary()
            node = Binary(":", node, right)
        return node

    def _rel(self, ref: CellRef, sheet) -> Ref:
        return Ref(ref.row if ref.row_abs else ref.row - self.row,
                   ref.col if ref.col_abs else ref.col - self.col,
                   ref.row_abs, ref.col_abs, sheet)

    def primary(self):
        tok = self.take()
        kind = tok.kind
        if kind == "num":
            node = Num(float(tok.text))
            return self._maybe_unit(node)
        if kind == "str":
            return Str(tok.text[1:-1].replace('""', '"'))
        if kind == "bool":
            return Bool(tok.text.upper() == "TRUE")
        if kind == "err":
            return BadRef() if tok.text == "#REF!" else Err(tok.text)
        if kind == "unit":
            return Unit(tok.text[1:])
        if kind == "ref":
            ref = tok.ref
            if isinstance(ref, CellRef):
                return self._rel(ref, ref.sheet)
            whole = ref.whole
            first, last = ref.first, ref.last
            return Area(self._rel(first, None), self._rel(last, None), whole, ref.sheet)
        if kind == "name":
            text = tok.text
            sheet = None
            if "!" in text:
                sheet, _, text = text.partition("!")
            self.names.add(text)
            return Name(text, sheet)
        if kind == "func":
            return self.call(tok)
        if kind == "(":
            node = self.expr(0)
            self.expect(")")
            return node
        if kind == "{":
            return self.array()
        raise FormulaError("There's a problem with this formula.", tok.pos)

    def _maybe_unit(self, number):
        """5 kN, 10 kN/m, 3 m^2: a unit written after a number."""
        tok = self.peek()
        if tok.kind == "unit":
            self.take()
            return Binary("*", number, Unit(tok.text[1:]))
        if tok.kind != "name" or "!" in tok.text or not is_unit_text(tok.text):
            return number
        parts = [tok.text]
        j = self.i + 1
        while True:
            t = self.peek(j - self.i)
            if t.kind == "op" and t.text == "^" and self.peek(j - self.i + 1).kind == "num":
                parts.append("^" + self.peek(j - self.i + 1).text)
                j += 2
                continue
            if t.kind == "op" and t.text == "^" and self.peek(j - self.i + 1).kind == "op" \
                    and self.peek(j - self.i + 1).text == "-" and self.peek(j - self.i + 2).kind == "num":
                parts.append("^-" + self.peek(j - self.i + 2).text)
                j += 3
                continue
            if t.kind == "op" and t.text in ("*", "/", "·"):
                nxt = self.peek(j - self.i + 1)
                if nxt.kind == "name" and "!" not in nxt.text and is_unit_text(nxt.text):
                    parts.append(("*" if t.text != "/" else "/") + nxt.text)
                    j += 2
                    continue
            break
        unit = "".join(parts)
        if not is_unit_text(unit):
            return number
        self.i = j
        return Binary("*", number, Unit(_pretty_unit(unit)))

    def call(self, tok: Token):
        name = tok.text.upper()
        if name.startswith("_XLFN."):
            name = name[6:]
        if name.startswith("_XLWS."):
            name = name[6:]
        self.expect("(")
        if name == "VAR" and self.peek(1).kind == ")" and (
                (self.peek().kind == "ref" and isinstance(self.peek().ref, CellRef)
                 and self.peek().ref.sheet is None and "$" not in self.peek().text)
                or (self.peek().kind == "name" and "!" not in self.peek().text)):
            # var(M20): the document variable M20 (Excel's VAR of one value
            # is always #DIV/0!, so nothing is lost); VAR(A1:A9) and
            # VAR(1,2,3) are Excel's variance
            inner = self.take()
            self.expect(")")
            self.names.add(inner.text)
            return DocVar(inner.text)
        self.functions.add(name)
        args = []
        if self.peek().kind == ")":
            self.take()
            return Call(name, ())
        while True:
            if self.peek().kind in (",", ")"):
                args.append(Missing())
            else:
                args.append(self.expr(0))
            tok2 = self.take()
            if tok2.kind == ")":
                break
            if tok2.kind != ",":
                raise FormulaError("Expected “,” or “)”.", tok2.pos)
        return Call(name, tuple(args))

    def array(self):
        rows, row = [], []
        while True:
            tok = self.take()
            sign = 1.0
            if tok.kind == "op" and tok.text in ("-", "+"):
                sign = -1.0 if tok.text == "-" else 1.0
                tok = self.take()
            if tok.kind == "num":
                row.append(Num(sign * float(tok.text)))
            elif tok.kind == "str":
                row.append(Str(tok.text[1:-1].replace('""', '"')))
            elif tok.kind == "bool":
                row.append(Bool(tok.text.upper() == "TRUE"))
            elif tok.kind == "err":
                row.append(Err(tok.text))
            else:
                raise FormulaError("An array may hold only numbers, text, TRUE/FALSE and errors.", tok.pos)
            sep = self.take()
            if sep.kind == ",":
                continue
            rows.append(tuple(row))
            row = []
            if sep.kind == ";":
                continue
            if sep.kind == "}":
                break
            raise FormulaError("Expected “,”, “;” or “}”.", sep.pos)
        if len({len(r) for r in rows}) != 1:
            raise FormulaError("Every row of an array must be as long.", 0)
        return ArrayLit(tuple(rows))


def _pretty_unit(unit: str) -> str:
    return unit


def _signature(tokens: list[Token], row: int, col: int) -> str:
    """The formula's text with relative references written as offsets: the
    same for every copy of a filled formula."""
    parts = []
    for t in tokens:
        if t.kind == "ref":
            ref = t.ref
            if isinstance(ref, CellRef):
                parts.append(_rel_text(ref, row, col))
            else:
                parts.append(f"{ref.sheet}!{ref.whole}{_rel_text(ref.first, row, col)}:{_rel_text(ref.last, row, col)}")
        else:
            parts.append(t.lead + t.text)
    return "\x00".join(parts)


def _rel_text(ref: CellRef, row: int, col: int) -> str:
    r = f"R{ref.row}" if ref.row_abs else f"R[{ref.row - row}]"
    c = f"C{ref.col}" if ref.col_abs else f"C[{ref.col - col}]"
    return f"{ref.sheet}!{r}{c}"


@lru_cache(maxsize=20000)
def _compiled(signature: str, text: str, row: int, col: int) -> Parsed:
    tokens = tokenize(text)
    p = _Parser(tokens, row, col)
    tree = p.parse()
    return Parsed(tree, bool(p.functions & VOLATILE), frozenset(p.names), frozenset(p.functions))


def parse(text: str, row: int = 0, col: int = 0) -> Parsed:
    """The tree of a formula (text without "=") written in cell (row, col).
    Raises FormulaError."""
    tokens = tokenize(text)
    sig = _signature(tokens, row, col)
    hit = _by_signature.get(sig)
    if hit is not None:
        return hit
    p = _Parser(tokens, row, col)
    tree = p.parse()
    parsed = Parsed(tree, bool(p.functions & VOLATILE), frozenset(p.names), frozenset(p.functions))
    if len(_by_signature) > 50000:
        _by_signature.clear()
    _by_signature[sig] = parsed
    return parsed


_by_signature: dict = {}


# -- what a formula refers to ----------------------------------------------------------
def references(tree, row: int, col: int):
    """(sheet or None, top, left, bottom, right) of every cell or block the
    formula reads directly, its cell being (row, col)."""
    out = []

    def walk(n):
        if isinstance(n, Ref):
            r, c = n.at(row, col)
            out.append((n.sheet, r, c, r, c))
        elif isinstance(n, Area):
            r1, c1 = n.first.at(row, col)
            r2, c2 = n.last.at(row, col)
            out.append((n.sheet, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)))
        elif isinstance(n, Binary):
            walk(n.left)
            walk(n.right)
        elif isinstance(n, (Unary, Percent)):
            walk(n.arg)
        elif isinstance(n, Call):
            for a in n.args:
                walk(a)

    walk(tree)
    return out


# -- rewriting references ------------------------------------------------------------------
RefMap = Callable[[object, Optional[str]], object]


def rewrite(text: str, change: RefMap) -> str:
    """The formula with every reference passed through change(ref, sheet):
    it returns the new CellRef/RangeRef, None for #REF!, or the same ref."""
    tokens = tokenize(text)
    changed = False
    for t in tokens:
        if t.kind != "ref":
            continue
        new = change(t.ref, t.ref.sheet)
        if new is t.ref:
            continue
        changed = True
        if new is None:
            t.text = (quote_sheet(t.ref.sheet) + "!" if t.ref.sheet else "") + "#REF!"
            t.kind = "err"
        else:
            t.text = new.a1(True)
            t.ref = new
    if not changed:
        return text
    return join(tokens)


def rename_sheet_in(text: str, old: str, new: str) -> str:
    """References to sheet ``old`` now name ``new`` (also Old!Name)."""
    tokens = tokenize(text)
    changed = False
    for t in tokens:
        if t.kind == "ref" and t.ref.sheet is not None and t.ref.sheet.lower() == old.lower():
            t.ref = replace(t.ref, sheet=new)
            t.text = t.ref.a1(True)
            changed = True
        elif t.kind == "name" and "!" in t.text:
            sheet, _, rest = t.text.partition("!")
            from .refs import unquote_sheet

            if (unquote_sheet(sheet) or "").lower() == old.lower():
                t.text = quote_sheet(new) + "!" + rest
                changed = True
        elif t.kind == "func" and False:
            pass
    if not changed:
        return text
    # sheet names inside text arguments of INDIRECT are left alone, as Excel does
    return join(tokens)


def moved_formula(text: str, drow: int, dcol: int) -> str:
    """The formula copied by (drow, dcol): relative references follow."""
    if drow == 0 and dcol == 0:
        return text
    return rewrite(text, lambda ref, sheet: ref.moved(drow, dcol))


def cycle_reference_at(text: str, caret: int) -> tuple[str, int]:
    """F4 on the reference at the caret: A1 -> $A$1 -> A$1 -> $A1 -> A1.
    Returns the new text and caret."""
    tokens = tokenize(text)
    at = 0
    for t in tokens:
        start = at + len(t.lead)
        end = start + len(t.text)
        if t.kind == "ref" and start <= caret <= end:
            ref = t.ref
            if isinstance(ref, CellRef):
                new = ref.cycled()
            else:
                new = replace(ref, first=ref.first.cycled(), last=ref.last.cycled())
            t.text = new.a1(True)
            t.ref = new
            new_text = join(tokens)
            return new_text, start + len(t.text)
        at = end
    return text, caret


def reference_spans(text: str) -> list[tuple[int, int, object]]:
    """(start, end, ref) of each reference in the text (without "="), for
    colouring references and their cells while a formula is typed."""
    out = []
    try:
        tokens = tokenize(text)
    except FormulaError:
        return out
    at = 0
    for t in tokens:
        start = at + len(t.lead)
        end = start + len(t.text)
        if t.kind == "ref":
            out.append((start, end, t.ref))
        at = end
    return out
