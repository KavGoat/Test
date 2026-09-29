"""Expression tree produced by parsing a :class:`~websmath.engine.model.Row`.

Every node remembers where it came from (``src`` = (row, start, end)) so an
error can outline the exact part of the equation the way SMath does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(eq=False)
class Node:
    src: Any = field(default=None, repr=False, compare=False, kw_only=True)


@dataclass(eq=False)
class Num(Node):
    text: str


@dataclass(eq=False)
class Var(Node):
    name: str  # includes the literal subscript: "L.A"


@dataclass(eq=False)
class UnitRef(Node):
    name: str  # without the leading apostrophe


@dataclass(eq=False)
class Str(Node):
    text: str


@dataclass(eq=False)
class Placeholder(Node):
    pass


@dataclass(eq=False)
class BinOp(Node):
    op: str
    left: Node
    right: Node
    implicit: bool = False  # number·unit written without the dot


@dataclass(eq=False)
class Unary(Node):
    op: str  # "-", "+", "!" (postfix), "¬"
    arg: Node


@dataclass(eq=False)
class Call(Node):
    name: str
    args: list


@dataclass(eq=False)
class IndexOp(Node):
    base: Node
    indices: list


@dataclass(eq=False)
class Group(Node):
    """Explicit brackets typed by the user."""

    inner: Node


@dataclass(eq=False)
class MatrixLit(Node):
    nrows: int
    ncols: int
    cells: list  # row-major


@dataclass(eq=False)
class Define(Node):
    target: Node  # Var, Call (function definition) or IndexOp
    value: Node


@dataclass(eq=False)
class Evaluate(Node):
    expr: Node


def walk(n: Node):
    yield n
    for v in n.__dict__.values():
        if isinstance(v, Node):
            yield from walk(v)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, Node):
                    yield from walk(x)
