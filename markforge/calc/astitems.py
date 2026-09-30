"""Expression tree -> editor items (the boxes the equation editor edits).

Used by symbolic results and by pasting. It came out of WebSMath's .sm
module, which CalcForge does not have (decision 2): only this part was
not about files."""
from __future__ import annotations

from .engine import ast as A
from .engine.model import Abs, Frac, Index, Matrix, Paren, Pow, Program, Root, Row, Sqrt


PREC = {"≔": 0, "=": 0, "∨": 1, "⊕": 1, "∧": 2, "<": 3, ">": 3, "≤": 3, "≥": 3, "≠": 3, "≡": 3,
        "+": 4, "-": 4, "±": 4, "*": 5, "/": 6, "^": 7}


def _prec(n: A.Node) -> int:
    if isinstance(n, A.BinOp):
        return PREC.get(n.op, 5)
    if isinstance(n, A.Unary):
        return 4 if n.op in "-+" else 8
    if isinstance(n, A.Define):
        return 0
    return 9


def _chars(s: str) -> list:
    return list(s)


def ast_to_items(n: A.Node, parent_prec: int = 0) -> list:
    items = _node_items(n)
    if isinstance(n, (A.BinOp, A.Unary)) and _prec(n) < parent_prec and not (
            isinstance(n, A.BinOp) and n.op == "/"):
        return [Paren(Row(items))]
    return items


def _row(n: A.Node, prec: int = 0) -> Row:
    return Row(ast_to_items(n, prec))


def _node_items(n: A.Node) -> list:
    if isinstance(n, A.Num):
        return _chars(n.text)
    if isinstance(n, A.Var):
        return _chars(n.name)
    if isinstance(n, A.UnitRef):
        return ["'"] + _chars(n.name)
    if isinstance(n, A.Str):
        return ['"'] + _chars(n.text) + ['"']
    if isinstance(n, A.Placeholder):
        return []
    if isinstance(n, A.Group):
        return [Paren(_row(n.inner))]
    if isinstance(n, A.Define):
        return ast_to_items(n.target) + ["≔"] + ast_to_items(n.value)
    if isinstance(n, A.Unary):
        if n.op == "!":
            return ast_to_items(n.arg, 8) + ["!"]
        return [n.op] + ast_to_items(n.arg, 5)
    if isinstance(n, A.BinOp):
        p = _prec(n)
        if n.op == "/":
            return [Frac(_row(n.left), _row(n.right))]
        if n.op == "^":
            return ast_to_items(n.left, 8) + [Pow(_row(n.right))]
        right = ast_to_items(n.right, p + (1 if n.op in "-" else 0))
        # number·unit written without the dot in SMath files
        if n.op == "*" and isinstance(n.right, A.UnitRef) and isinstance(n.left, (A.Num, A.BinOp)):
            return ast_to_items(n.left, p) + right
        return ast_to_items(n.left, p) + [n.op] + right
    if isinstance(n, A.Call):
        return _call_items(n)
    if isinstance(n, A.IndexOp):
        return ast_to_items(n.base, 8) + [Index(Row(_join_args(n.indices)))]
    if isinstance(n, A.MatrixLit):
        return [Matrix(n.nrows, n.ncols, [_row(c) for c in n.cells])]
    return []


def _join_args(args) -> list:
    out = []
    for k, a in enumerate(args):
        if k:
            out.append(",")
        out += ast_to_items(a)
    return out


def _call_items(n: A.Call) -> list:
    name, args = n.name, n.args
    if name == "sqrt" and len(args) == 1:
        return [Sqrt(_row(args[0]))]
    if name == "nthroot" and len(args) == 2:
        return [Root(_row(args[1]), _row(args[0]))]
    if name == "abs" and len(args) == 1:
        return [Abs(_row(args[0]))]
    if name == "el" and len(args) in (2, 3):
        return ast_to_items(args[0], 8) + [Index(Row(_join_args(args[1:])))]
    if name == "mat" and len(args) >= 3:
        try:
            r, c = int(args[-2].text), int(args[-1].text)
            cells = args[:-2]
            if len(cells) == r * c:
                return [Matrix(r, c, [_row(x) for x in cells])]
        except (AttributeError, ValueError):
            pass
    if name == "line" and len(args) >= 3:
        # SMath stores a line block as line(s1, ..., sn, n, 1): the last two
        # operands are its size, not statements (shown or evaluated they
        # made the block's value 1 and drew "1 1" under the statements)
        try:
            if int(args[-2].text) == len(args) - 2 and int(args[-1].text) == 1:
                args = args[:-2]
        except (AttributeError, ValueError):
            pass
    if name in ("if", "line", "while", "for") and args:
        return [Program(name, *[_row(a) for a in args])]
    return _chars(name) + [Paren(Row(_join_args(args)))]


# ---------------------------------------------------------------------------
# AST -> RPN
# ---------------------------------------------------------------------------
