"""Parse an editor :class:`Row` into an AST.

Precedence, lowest first (as SMath):
    ≔ (definition), = (evaluation)
    ∨ ⊕, ∧
    comparisons  < > ≤ ≥ ≠ ≡
    + -
    · × (and implicit number·unit)
    unary - ¬
    power (a Pow box binds to the operand on its left), postfix !, index
    primaries: numbers, names, 'units, "strings", brackets, calls, boxes
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import ast as A
from .model import (DIGITS, LETTERS, Abs, Box, Frac, Index, Matrix, Paren, Pow,
                    Program, Root, Row, Sqrt)


class ParseError(Exception):
    def __init__(self, message: str, src=None):
        super().__init__(message)
        self.src = src


@dataclass
class Tok:
    kind: str  # num ident unit str op sep box
    value: object
    start: int
    end: int


def _is_ident_char(c: str) -> bool:
    return c in LETTERS or c in DIGITS or c == "."


def lex(r: Row) -> list[Tok]:
    toks: list[Tok] = []
    items = r.items
    i, n = 0, len(items)
    while i < n:
        it = items[i]
        if isinstance(it, Box):
            toks.append(Tok("box", it, i, i + 1))
            i += 1
            continue
        c = it
        if c in DIGITS or (c == "." and i + 1 < n and items[i + 1] in DIGITS):
            j = i
            while j < n and isinstance(items[j], str) and (items[j] in DIGITS or items[j] == "."):
                j += 1
            toks.append(Tok("num", "".join(items[i:j]), i, j))
            i = j
        elif c == "'":
            j = i + 1
            while j < n and isinstance(items[j], str) and _is_ident_char(items[j]) and items[j] != "'":
                j += 1
            toks.append(Tok("unit", "".join(items[i + 1:j]), i, j))
            i = j
        elif c == '"':
            j = i + 1
            while j < n and items[j] != '"':
                j += 1
            text = "".join(x for x in items[i + 1:j] if isinstance(x, str))
            toks.append(Tok("str", text, i, min(j + 1, n)))
            i = j + 1
        elif c in LETTERS:
            j = i
            while j < n and isinstance(items[j], str) and _is_ident_char(items[j]) and items[j] not in "'\"":
                j += 1
            toks.append(Tok("ident", "".join(items[i:j]), i, j))
            i = j
        elif c in ",;":
            toks.append(Tok("sep", c, i, i + 1))
            i += 1
        elif c == " ":
            i += 1
        else:
            toks.append(Tok("op", c, i, i + 1))
            i += 1
    return toks


class Parser:
    def __init__(self, r: Row):
        self.row = r
        self.toks = lex(r)
        self.pos = 0

    # -- helpers --------------------------------------------------------------
    def peek(self, k: int = 0) -> Optional[Tok]:
        p = self.pos + k
        return self.toks[p] if p < len(self.toks) else None

    def take(self) -> Tok:
        t = self.toks[self.pos]
        self.pos += 1
        return t

    def at_op(self, *ops: str) -> bool:
        t = self.peek()
        return t is not None and t.kind == "op" and t.value in ops

    def src(self, a: int, b: int):
        return (self.row, a, b)

    # -- grammar --------------------------------------------------------------
    def parse(self) -> A.Node:
        if not self.toks:
            return A.Placeholder(src=self.src(0, 0))
        node = self.statement()
        if self.peek() is not None:
            t = self.peek()
            raise ParseError("Syntax error.", self.src(t.start, t.end))
        return node

    def statement(self) -> A.Node:
        start = self.peek().start if self.peek() else 0
        left = self.boolean()
        if self.at_op("≔"):
            self.take()
            right = self.boolean() if self.peek() else A.Placeholder(src=self.src(len(self.row), len(self.row)))
            left = A.Define(left, right, src=self.src(start, self._end()))
        if self.at_op("="):
            self.take()
            left = A.Evaluate(left, src=self.src(start, self._end()))
        return left

    def _end(self) -> int:
        return self.toks[self.pos - 1].end if self.pos else 0

    def _bin(self, sub, ops):
        start = self.peek().start if self.peek() else 0
        left = sub()
        while self.at_op(*ops):
            op = self.take().value
            right = sub() if self.peek() and not self._at_stop() else A.Placeholder(src=self.src(self._end(), self._end()))
            left = A.BinOp(op, left, right, src=self.src(start, self._end()))
        return left

    def _at_stop(self) -> bool:
        t = self.peek()
        return t is None or (t.kind == "op" and t.value in ("=", "≔")) or t.kind == "sep"

    def boolean(self):
        return self._bin(self.conj, ("∨", "⊕"))

    def conj(self):
        return self._bin(self.compare, ("∧",))

    def compare(self):
        return self._bin(self.additive, ("<", ">", "≤", "≥", "≠", "≡", "≈", "≉"))

    def additive(self):
        return self._bin(self.multiplicative, ("+", "-", "±"))

    def multiplicative(self):
        start = self.peek().start if self.peek() else 0
        left = self.unary()
        while True:
            if self.at_op("*", "×", "/", "†"):
                op = self.take().value
                op = {"×": "*"}.get(op, op)
                right = self.unary() if not self._at_stop() else A.Placeholder(src=self.src(self._end(), self._end()))
                left = A.BinOp(op, left, right, src=self.src(start, self._end()))
            elif self._implicit_follows(left):
                right = self.unary()
                left = A.BinOp("*", left, right, implicit=True, src=self.src(start, self._end()))
            else:
                return left

    def _implicit_follows(self, left) -> bool:
        t = self.peek()
        if t is None:
            return False
        # 3'mm, 2'kN*... : a unit right after a value multiplies it, and so
        # does a unit fraction (2 kN/m is 2·(kN/m)).
        if t.kind == "unit":
            return True
        return t.kind == "box" and isinstance(t.value, Frac) and starts_with_unit(t.value.rows[0])

    def unary(self):
        t = self.peek()
        if t and t.kind == "op" and t.value in ("-", "+", "¬", "±"):
            self.take()
            arg = self.unary() if not self._at_stop() else A.Placeholder(src=self.src(t.end, t.end))
            return A.Unary(t.value, arg, src=self.src(t.start, self._end()))
        return self.postfix()

    def postfix(self):
        start = self.peek().start if self.peek() else 0
        node = self.primary()
        while True:
            t = self.peek()
            if t is None:
                return node
            if t.kind == "box" and isinstance(t.value, Pow):
                self.take()
                exp = parse_row(t.value.rows[0])
                node = A.BinOp("^", node, exp, src=self.src(start, t.end))
            elif t.kind == "box" and isinstance(t.value, Index):
                self.take()
                idx = split_args(t.value.rows[0])
                node = A.IndexOp(node, idx, src=self.src(start, t.end))
            elif t.kind == "op" and t.value == "!":
                self.take()
                node = A.Unary("!", node, src=self.src(start, t.end))
            else:
                return node

    def primary(self):
        t = self.peek()
        if t is None or t.kind == "sep" or (t.kind == "op" and t.value in (
                "=", "≔", "*", "/", "<", ">", "≤", "≥", "≠", "≡", "∧", "∨", "⊕", "†", "≈", "≉")):
            p = t.start if t else len(self.row)
            return A.Placeholder(src=self.src(p, p))
        self.take()
        s = self.src(t.start, t.end)
        if t.kind == "num":
            return A.Num(t.value, src=s)
        if t.kind == "unit":
            return A.UnitRef(t.value, src=s)
        if t.kind == "str":
            return A.Str(t.value, src=s)
        if t.kind == "ident":
            nxt = self.peek()
            if nxt and nxt.kind == "box" and isinstance(nxt.value, Paren):
                self.take()
                args = split_args(nxt.value.rows[0])
                return A.Call(t.value, args, src=self.src(t.start, nxt.end))
            return A.Var(t.value, src=s)
        if t.kind == "box":
            return box_node(t.value, s)
        raise ParseError("Syntax error.", s)


def starts_with_unit(r: Row) -> bool:
    return bool(r.items) and r.items[0] == "'"


def split_args(r: Row) -> list[A.Node]:
    """Split a row on top-level separators and parse each piece."""
    pieces: list[tuple[int, int]] = []
    start = 0
    for i, it in enumerate(r.items):
        if isinstance(it, str) and it in ",;":
            pieces.append((start, i))
            start = i + 1
    pieces.append((start, len(r.items)))
    if len(pieces) == 1 and not r.items:
        return [A.Placeholder(src=(r, 0, 0))]
    out = []
    for a, b in pieces:
        sub = Row()
        sub.items = r.items[a:b]
        p = Parser(sub)
        p.row = r
        # re-base token positions onto the parent row
        for tk in p.toks:
            tk.start += a
            tk.end += a
        if not p.toks:
            out.append(A.Placeholder(src=(r, a, a)))
            continue
        node = p.statement()  # arguments may hold definitions: s:=s+i
        if p.peek() is not None:
            t = p.peek()
            raise ParseError("Syntax error.", (r, t.start, t.end))
        out.append(node)
    return out


def box_node(b: Box, s) -> A.Node:
    if isinstance(b, Frac):
        return A.BinOp("/", parse_row(b.rows[0]), parse_row(b.rows[1]), src=s)
    if isinstance(b, Sqrt):
        return A.Call("sqrt", [parse_row(b.rows[0])], src=s)
    if isinstance(b, Root):
        return A.Call("nthroot", [parse_row(b.rows[1]), parse_row(b.rows[0])], src=s)
    if isinstance(b, Abs):
        return A.Call("abs", [parse_row(b.rows[0])], src=s)
    if isinstance(b, Paren):
        args = split_args(b.rows[0])
        if len(args) == 1:
            return A.Group(args[0], src=s)
        return A.Call("", args, src=s)
    if isinstance(b, Matrix):
        return A.MatrixLit(b.nrows, b.ncols, [parse_row(c) for c in b.rows], src=s)
    if isinstance(b, Program):
        return A.Call(b.name, [parse_row(c) for c in b.rows], src=s)
    raise ParseError("Syntax error.", s)


def parse_row(r: Row) -> A.Node:
    return Parser(r).parse()
