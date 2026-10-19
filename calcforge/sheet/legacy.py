"""Excel's implicit intersection, for formulas written before dynamic arrays.

A formula an .xlsx stores as a plain formula (not an array formula) is
worked out the way Excel did before dynamic arrays: where a block of cells
— a defined name of a block (``s_x = $J$17:$J$39``), a block reference, or
what INDIRECT or OFFSET give — stands where one value is wanted, the cell of
the block in the formula's own row (a column) or column (a row) is taken.
``=s_x*w`` on row 17 multiplies J17 by F17. Excel 365 shows this as ``@``
(``=@s_x*@w``) when it opens such a file, and keeps the meaning; here the
``@`` is written into the formula the same way (:func:`with_intersections`),
so the cell gives Excel's answer and shows why.

Where a value is wanted depends on what each function takes there
(:data:`_PARAMS`): SUM, COUNTIF's range or VLOOKUP's table take a block as
it is; INDEX, LOOKUP and SUMPRODUCT take arrays, and whatever is inside them
is worked out over the whole block; every other argument, and the operands
of + - * / ^ & = < >, take one value.
"""
from __future__ import annotations

from typing import Callable, Optional

from . import formula as F
from .refs import CellRef

VALUE, REF, ARRAY, PASS = "value", "ref", "array", "pass"

_ALL_REF = ("SUM", "AVERAGE", "AVERAGEA", "MIN", "MINA", "MAX", "MAXA", "COUNT", "COUNTA",
            "COUNTBLANK", "PRODUCT", "STDEV", "STDEVA", "STDEVP", "STDEVPA", "STDEV.S", "STDEV.P",
            "VAR", "VARA", "VARP", "VARPA", "VAR.S", "VAR.P", "MEDIAN", "MODE", "MODE.SNGL",
            "MODE.MULT", "AVEDEV", "DEVSQ", "GEOMEAN", "HARMEAN", "KURT", "SKEW", "SUMSQ", "AND",
            "OR", "XOR", "CONCAT", "ROWS", "COLUMNS", "AREAS", "ISREF", "ROW", "COLUMN",
            "IRR", "MAXIFS", "MINIFS")
_ALL_ARRAY = ("SUMPRODUCT", "MMULT", "MDETERM", "MINVERSE", "TRANSPOSE", "FREQUENCY", "LINEST",
              "LOGEST", "TREND", "GROWTH", "SUMX2MY2", "SUMX2PY2", "SUMXMY2", "CORREL", "PEARSON",
              "RSQ", "SLOPE", "INTERCEPT", "STEYX", "COVAR", "COVARIANCE.P", "COVARIANCE.S",
              "PROB", "TTEST", "T.TEST", "CHITEST", "CHISQ.TEST")

#: what each argument of a function takes: (first arguments..., the rest)
_PARAMS: dict = {name: ((), REF) for name in _ALL_REF}
_PARAMS.update({name: ((), ARRAY) for name in _ALL_ARRAY})
_PARAMS.update({
    "SUMIF": ((REF, VALUE, REF), VALUE),
    "AVERAGEIF": ((REF, VALUE, REF), VALUE),
    "COUNTIF": ((REF, VALUE), VALUE),
    "INDEX": ((ARRAY,), VALUE),
    "MATCH": ((VALUE, REF), VALUE),
    "XMATCH": ((VALUE, REF), VALUE),
    "VLOOKUP": ((VALUE, REF), VALUE),
    "HLOOKUP": ((VALUE, REF), VALUE),
    "LOOKUP": ((VALUE, ARRAY, ARRAY), VALUE),
    "XLOOKUP": ((VALUE, REF, REF), VALUE),
    "OFFSET": ((REF,), VALUE),
    "IF": ((VALUE, PASS, PASS), VALUE),
    "CHOOSE": ((VALUE,), PASS),
    "LARGE": ((ARRAY,), VALUE), "SMALL": ((ARRAY,), VALUE),
    "PERCENTILE": ((ARRAY,), VALUE), "PERCENTILE.INC": ((ARRAY,), VALUE),
    "PERCENTILE.EXC": ((ARRAY,), VALUE), "QUARTILE": ((ARRAY,), VALUE),
    "QUARTILE.INC": ((ARRAY,), VALUE), "QUARTILE.EXC": ((ARRAY,), VALUE),
    "PERCENTRANK": ((ARRAY,), VALUE), "PERCENTRANK.INC": ((ARRAY,), VALUE),
    "PERCENTRANK.EXC": ((ARRAY,), VALUE),
    "RANK": ((VALUE, REF), VALUE), "RANK.EQ": ((VALUE, REF), VALUE),
    "RANK.AVG": ((VALUE, REF), VALUE),
    "FORECAST": ((VALUE, ARRAY, ARRAY), VALUE), "FORECAST.LINEAR": ((VALUE, ARRAY, ARRAY), VALUE),
    "NPV": ((VALUE,), REF), "MIRR": ((REF,), VALUE),
    "SUBTOTAL": ((VALUE,), REF), "AGGREGATE": ((VALUE, VALUE), REF),
    "TEXTJOIN": ((VALUE, VALUE), REF),
    "CELL": ((VALUE, REF), VALUE),
    "DSUM": ((REF, VALUE, REF), VALUE), "DCOUNT": ((REF, VALUE, REF), VALUE),
    "DCOUNTA": ((REF, VALUE, REF), VALUE), "DAVERAGE": ((REF, VALUE, REF), VALUE),
    "DMAX": ((REF, VALUE, REF), VALUE), "DMIN": ((REF, VALUE, REF), VALUE),
    "DGET": ((REF, VALUE, REF), VALUE), "DPRODUCT": ((REF, VALUE, REF), VALUE),
    "SERIESSUM": ((VALUE, VALUE, VALUE, ARRAY), VALUE),
})
# SUMIFS(sum range, range, criterion, range, criterion...), COUNTIFS(range, criterion...)
_PAIRED = {"SUMIFS": 1, "AVERAGEIFS": 1, "MAXIFS": 1, "MINIFS": 1, "COUNTIFS": 0}

#: functions that give a block of cells from what they are told
_GIVE_BLOCKS = {"INDIRECT", "OFFSET"}


def _param(name: str, index: int) -> str:
    start = _PAIRED.get(name)
    if start is not None:
        if index < start:
            return REF
        return REF if (index - start) % 2 == 0 else VALUE
    first, rest = _PARAMS.get(name, ((), VALUE))
    return first[index] if index < len(first) else rest


# -- a small tree of the formula's tokens -------------------------------------------------
class _Node:
    __slots__ = ("kind", "at", "name", "kids")

    def __init__(self, kind: str, at: int = -1, name: str = "", kids=()):
        self.kind = kind          # leaf name block call bin range neg at paren
        self.at = at              # the token where an @ would go
        self.name = name
        self.kids = list(kids)


class _Reader:
    """Mirrors formula._Parser over the tokens, keeping where each part starts."""

    def __init__(self, tokens):
        self.t = tokens
        self.i = 0

    def peek(self, k: int = 0):
        return self.t[min(self.i + k, len(self.t) - 1)]

    def take(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expr(self, min_prec: int = 0) -> _Node:
        left = self.unary()
        while True:
            tok = self.peek()
            if tok.kind != "op" or tok.text not in F._PREC:
                break
            prec = F._PREC[tok.text]
            if prec < min_prec:
                break
            self.take()
            right = self.expr(prec + 1)
            left = _Node("bin", left.at, kids=(left, right))
        return left

    def unary(self) -> _Node:
        tok = self.peek()
        if tok.kind == "op" and tok.text in ("-", "+", "@"):
            at = self.i
            self.take()
            arg = self.unary()
            return _Node("at" if tok.text == "@" else "neg", at, kids=(arg,))
        return self.postfix()

    def postfix(self) -> _Node:
        node = self.ranged()
        while self.peek().kind == "(" and node.kind == "call":
            self.take()                              # LAMBDA(x, x)(3)
            node = _Node("leaf", node.at, kids=[node] + self.args())
        while self.peek().kind == "op" and self.peek().text == "%":
            self.take()
            node = _Node("neg", node.at, kids=(node,))
        return node

    def ranged(self) -> _Node:
        node = self.primary()
        while self.peek().kind == "op" and self.peek().text == ":":
            self.take()
            right = self.primary()
            node = _Node("range", node.at, kids=(node, right))
        return node

    def args(self) -> list:
        out = []
        if self.peek().kind == ")":
            self.take()
            return out
        while True:
            if self.peek().kind in (",", ")"):
                out.append(_Node("leaf", self.i))
            else:
                out.append(self.expr(0))
            tok = self.take()
            if tok.kind == ")":
                return out
            if tok.kind != ",":
                raise F.FormulaError("Expected “,” or “)”.", tok.pos)

    def primary(self) -> _Node:
        at = self.i
        tok = self.take()
        kind = tok.kind
        if kind == "num":
            if self.peek().kind == "unit":
                self.take()
            return _Node("leaf", at)
        if kind == "ref":
            if isinstance(tok.ref, CellRef):
                if self.peek().kind == "#":
                    self.take()
                    return _Node("leaf", at)       # A1#: a spill, meant whole
                return _Node("leaf", at)
            return _Node("block", at)
        if kind == "name":
            return _Node("name", at, tok.text)
        if kind == "func":
            name = tok.text.upper()
            for prefix in ("_XLFN.", "_XLWS."):
                if name.startswith(prefix):
                    name = name[len(prefix):]
            if self.take().kind != "(":
                raise F.FormulaError("Expected “(”.", tok.pos)
            return _Node("call", at, name, self.args())
        if kind == "(":
            inner = self.expr(0)
            if self.take().kind != ")":
                raise F.FormulaError("Expected “)”.", tok.pos)
            return _Node("paren", at, kids=(inner,))
        if kind == "{":
            while self.take().kind != "}":
                pass
            return _Node("leaf", at)
        if kind in ("str", "bool", "err", "unit", "struct"):
            return _Node("leaf", at)
        raise F.FormulaError("There's a problem with this formula.", tok.pos)


def _walk(node: _Node, mode: str, block_name: Callable[[str], bool], marks: set) -> None:
    kind = node.kind
    if kind == "name":
        if mode == VALUE and block_name(node.name):
            marks.add(node.at)
    elif kind == "block":
        if mode == VALUE:
            marks.add(node.at)
    elif kind == "range":
        if mode == VALUE:
            marks.add(node.at)
        for kid in node.kids:
            _walk(kid, REF, block_name, marks)
    elif kind == "call":
        if mode == VALUE and node.name in _GIVE_BLOCKS:
            marks.add(node.at)
        for k, kid in enumerate(node.kids):
            want = _param(node.name, k)
            if mode == ARRAY:
                want = ARRAY
            elif want == PASS:
                want = mode
            _walk(kid, want, block_name, marks)
    elif kind in ("bin", "neg"):
        inner = ARRAY if mode == ARRAY else VALUE
        for kid in node.kids:
            _walk(kid, inner, block_name, marks)
    elif kind == "at":
        for kid in node.kids:
            _walk(kid, REF, block_name, marks)
    elif kind == "paren":
        _walk(node.kids[0], mode, block_name, marks)
    else:
        for kid in node.kids:
            _walk(kid, VALUE if mode != ARRAY else ARRAY, block_name, marks)


def with_intersections(text: str, block_name: Callable[[str], bool]) -> str:
    """*text* (a formula without its "=") with ``@`` written where Excel
    before dynamic arrays took one cell of a block. *block_name* says whether
    a name (as written: ``cdtA`` or ``Tables!cdtA``) stands for more than one
    cell. Unchanged when nothing needs one, or the formula can't be read."""
    try:
        tokens = F.tokenize(text)
        reader = _Reader(tokens)
        tree = reader.expr(0)
        if reader.peek().kind != "end":
            return text
    except (F.FormulaError, IndexError):
        return text
    marks: set = set()
    _walk(tree, VALUE, block_name, marks)
    if not marks:
        return text
    for i in marks:
        tokens[i].lead, tokens[i].text = tokens[i].lead + "@", tokens[i].text
    return F.join(tokens)


def names_of_blocks(names: list, sheets: dict) -> Callable[[str, Optional[str]], bool]:
    """block_name for a workbook's defined names: *names* as
    (name, refers to, sheet it is local to or None). A name of more than one
    cell, or of a formula (OFFSET(...)), is a block; a constant or a single
    cell is not."""
    blocks: dict = {}
    for name, refers_to, local in names:
        blocks[(name.lower(), (local or "").lower())] = _is_block(refers_to)

    def block_name(written: str, sheet: Optional[str]) -> bool:
        where, _, name = written.rpartition("!")
        where = where.strip("'").replace("''", "'").lower() if where else (sheet or "").lower()
        got = blocks.get((name.lower(), where))
        if got is None:
            got = blocks.get((name.lower(), ""))
        return bool(got)

    return block_name


def _is_block(refers_to: str) -> bool:
    try:
        tokens = [t for t in F.tokenize(refers_to) if t.kind != "end"]
    except F.FormulaError:
        return False
    if len(tokens) == 1:
        t = tokens[0]
        if t.kind == "ref":
            return not isinstance(t.ref, CellRef) and not (
                t.ref.top == t.ref.bottom and t.ref.left == t.ref.right)
        return False
    return any(t.kind == "func" or (t.kind == "op" and t.text == ":") for t in tokens)
