"""Expression parsing and evaluation.

The engine turns engineer-friendly source text into Python ASTs, evaluates them
against a :class:`Workspace`, and reports results as unit-aware quantities.

Supported statement forms (one per line)::

    # a comment                     comment, ignored
    b := 300 mm                     definition
    b = 300 mm                      definition (plain '=' also works)
    f(x) := x^2 + 1                 function definition
    A = b*d                         definition with a computed value
    b*d =                           evaluation, trailing '=' optional
    sigma -> MPa                    evaluation converted to a display unit

Implicit multiplication (``5 kN``, ``2(a+b)``), ``^`` for powers and a set of
unicode operators (``·``, ``×``, ``÷``, ``√``, ``≤``) are all accepted.
"""
from __future__ import annotations

import ast
import io
import keyword
import re
import tokenize
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pint

from . import functions as fnlib
from .units import (Q_, Quantity, SHADOWED_UNITS, convert, format_quantity,
                    preferred_unit, reads_well, simplify_units, ureg)

# ---------------------------------------------------------------------------
# Source normalisation
# ---------------------------------------------------------------------------

_UNICODE_MAP = {
    "−": "-", "–": "-", "—": "-",
    "×": "*", "·": "*", "∙": "*", "⋅": "*",
    "÷": "/", "∕": "/",
    "≤": "<=", "≥": ">=", "≠": "!=", "⩽": "<=", "⩾": ">=",
    "√": "sqrt", "π": "pi", "∞": "inf",
    "²": "^2", "³": "^3", "⁴": "^4", "½": "0.5", "¼": "0.25", "¾": "0.75",
    "µ": "u", "μ": "u", "Ω": "ohm", "Ω": "ohm",
    "°": " deg", "’": "'", "“": '"', "”": '"',
    " ": " ", "−": "-",
}

_ARROWS = ("→", "->", "⇒", "»")

# Function names that collide with Python keywords; written with a trailing
# underscore internally so that "if(x>0, a, b)" can be typed naturally.
KEYWORD_FUNCTIONS = {"if", "and", "or", "not", "is", "in", "lambda"}

# Names the evaluator refuses to look at, whatever the source says.
_FORBIDDEN = {
    "__import__", "eval", "exec", "compile", "open", "input", "globals",
    "locals", "vars", "getattr", "setattr", "delattr", "exit", "quit",
    "breakpoint", "memoryview", "object", "type", "super",
}

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Call,
    ast.Name, ast.Load, ast.Constant, ast.Tuple, ast.List, ast.Dict, ast.Set,
    ast.Subscript, ast.Slice, ast.IfExp, ast.Starred, ast.keyword,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.MatMult, ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.comprehension, ast.ListComp, ast.GeneratorExp, ast.Store, ast.Lambda,
    ast.arguments, ast.arg, ast.Attribute,
)


def normalise(text: str) -> str:
    """Replace typographic and unicode maths characters with ASCII."""
    for source, target in _UNICODE_MAP.items():
        if source in text:
            text = text.replace(source, target)
    return text


def _split_top_level(text: str, marker: str) -> Optional[tuple[str, str]]:
    """Split on the last occurrence of *marker* outside any bracket."""
    depth = 0
    index = -1
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and text.startswith(marker, i):
            index = i
            i += len(marker)
            continue
        i += 1
    if index < 0:
        return None
    return text[:index], text[index + len(marker):]


# ---------------------------------------------------------------------------
# Tokenisation: implicit multiplication and '^' powers
# ---------------------------------------------------------------------------

def _needs_star(prev: tuple[int, str], nxt: tuple[int, str]) -> bool:
    ptype, ptext = prev
    ntype, ntext = nxt
    if ptype == tokenize.NAME and keyword.iskeyword(ptext):
        return False
    if ntype == tokenize.NAME and keyword.iskeyword(ntext):
        return False
    if ptype == tokenize.NUMBER and ntype in (tokenize.NAME, tokenize.NUMBER):
        return True
    if ptype == tokenize.NUMBER and ntype == tokenize.OP and ntext == "(":
        return True
    if ptype == tokenize.NAME and ntype == tokenize.NUMBER:
        return True
    if ptype == tokenize.NAME and ntype == tokenize.NAME:
        return True
    if ptype == tokenize.OP and ptext == ")":
        if ntype in (tokenize.NAME, tokenize.NUMBER):
            return True
        if ntype == tokenize.OP and ntext == "(":
            return True
    return False


def transform(expr: str) -> str:
    """Rewrite an engineering expression into valid Python source."""
    expr = expr.strip()
    if not expr:
        return expr
    try:
        raw = list(tokenize.generate_tokens(io.StringIO(expr).readline))
    except (tokenize.TokenError, IndentationError):
        # Unbalanced brackets while the user is still typing.
        return expr.replace("^", "**")

    kept: list[tuple[int, str]] = []
    for index, token in enumerate(raw):
        if token.type in (tokenize.ENCODING, tokenize.NL, tokenize.NEWLINE,
                          tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER,
                          tokenize.COMMENT):
            continue
        text = token.string
        if token.type == tokenize.OP and text == "^":
            text = "**"
        elif token.type == tokenize.NAME and text in KEYWORD_FUNCTIONS:
            # "if(a, b, c)" reads better than "if_(a, b, c)"; accept both.
            following = raw[index + 1] if index + 1 < len(raw) else None
            if following is not None and following.string == "(":
                text = text + "_"
        kept.append((token.type, text))

    out: list[str] = []
    for index, item in enumerate(kept):
        if index and _needs_star(kept[index - 1], item):
            out.append("*")
        out.append(item[1])
    return " ".join(out)


def validate(tree: ast.AST) -> None:
    """Reject anything outside the safe arithmetic subset."""
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"{type(node).__name__} is not allowed in an expression")
        if isinstance(node, ast.Name) and (node.id in _FORBIDDEN or node.id.startswith("__")):
            raise ValueError(f"'{node.id}' is not available")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError("private attributes are not available")


# Calls whose arguments must NOT be evaluated until they are needed, so that
# ``if(b == 0, 0, a/b)`` and ``iferror(a/b, 0)`` behave the way a spreadsheet
# user expects rather than raising from the untaken branch.
LAZY_CALLS = {
    "if_": "_lazy_if", "ifelse": "_lazy_if",
    "iferror": "_lazy_iferror",
}


class _LazyCalls(ast.NodeTransformer):
    """Rewrite lazy calls so each argument becomes a zero-argument lambda."""

    def visit_Call(self, node: ast.Call) -> ast.Call:
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id in LAZY_CALLS and not node.keywords:
            replacement = ast.Call(
                func=ast.Name(id=LAZY_CALLS[node.func.id], ctx=ast.Load()),
                args=[ast.Lambda(
                    args=ast.arguments(posonlyargs=[], args=[], vararg=None,
                                       kwonlyargs=[], kw_defaults=[], kwarg=None,
                                       defaults=[]),
                    body=argument) for argument in node.args],
                keywords=[])
            return ast.copy_location(replacement, node)
        return node


def compile_expression(source: str, pre_transformers: tuple = ()
                       ) -> tuple[Any, ast.Expression]:
    """Transform, parse, validate and compile *source*.

    *pre_transformers* are :class:`ast.NodeTransformer` instances applied before
    validation, letting callers add their own surface syntax (the spreadsheet
    uses one for Excel's ``&`` concatenation operator).  The returned tree is
    the display tree — lazy-call rewriting only affects the compiled code.
    """
    python_source = transform(source)
    tree = ast.parse(python_source, mode="eval")
    for transformer in pre_transformers:
        tree = ast.fix_missing_locations(transformer.visit(tree))
    validate(tree)
    compiled_tree = ast.fix_missing_locations(_LazyCalls().visit(_clone(tree)))
    return compile(compiled_tree, "<calcforge>", "eval"), tree


def _clone(tree: ast.AST) -> ast.AST:
    import copy
    return copy.deepcopy(tree)


def evaluate_code(code, namespace: dict[str, Any]) -> Any:
    """Run compiled expression code against *namespace*.

    The namespace is supplied as globals (not locals) so that names used inside
    the lambdas produced by lazy-call rewriting still resolve.
    """
    namespace["__builtins__"] = {}
    return eval(code, namespace)


def _all_names(code) -> set[str]:
    names = set(code.co_names) | set(getattr(code, "co_varnames", ()))
    for const in code.co_consts:
        if hasattr(const, "co_names"):
            names |= _all_names(const)
    return names


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def is_unit_literal(tree) -> bool:
    """True when an expression is one number scaled by pure unit names.

    ``12 kN/m`` and ``896 cm^3`` are values the author entered, not results, so
    they keep the units they were written in rather than being normalised.
    """
    if tree is None:
        return False
    node = tree.body if isinstance(tree, ast.Expression) else tree
    while isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand
    if not isinstance(node, ast.BinOp):
        return False
    return _number_times_units(node)


def _number_times_units(node) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float))
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div)):
        return _number_times_units(node.left) and _pure_units(node.right)
    return False


def _pure_units(node) -> bool:
    """True for a unit-only expression such as ``kN``, ``m^3`` or ``kg*m/s^2``."""
    from .units import is_unit_name

    if isinstance(node, ast.Name):
        return is_unit_name(node.id)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            return (_pure_units(node.left) and isinstance(node.right, ast.Constant)
                    and isinstance(node.right.value, (int, float)))
        if isinstance(node.op, (ast.Mult, ast.Div)):
            return _pure_units(node.left) and _pure_units(node.right)
    return False


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, pint.DimensionalityError):
        return (f"Units do not match: cannot combine "
                f"{exc.units1 or 'dimensionless'} with {exc.units2 or 'dimensionless'}")
    if isinstance(exc, pint.UndefinedUnitError):
        return f"Unknown unit or name: {exc.unit_names}"
    if isinstance(exc, NameError):
        match = re.search(r"'([^']+)'", str(exc))
        return f"'{match.group(1)}' is not defined" if match else str(exc)
    if isinstance(exc, ZeroDivisionError):
        return "Division by zero"
    if isinstance(exc, SyntaxError):
        return "Syntax error"
    if isinstance(exc, TypeError) and "not callable" in str(exc):
        return "Value used as a function — did you mean multiplication?"
    if isinstance(exc, TypeError) and "compare" in str(exc).lower():
        return "Cannot compare a value that has units with a plain number"
    return str(exc) or type(exc).__name__


def _lazy_if(condition: Callable, when_true: Callable, when_false: Callable = None):
    """Evaluate only the branch that is actually taken."""
    truth = condition()
    if isinstance(truth, Quantity):
        truth = truth.magnitude
    if truth:
        return when_true()
    return when_false() if when_false is not None else 0


def _lazy_iferror(value: Callable, fallback: Callable):
    """Return *value*, or *fallback* when evaluating it raises."""
    try:
        result = value()
    except Exception:
        return fallback()
    if type(result).__name__ == "CellError":
        return fallback()
    return result


# ---------------------------------------------------------------------------
# User-defined functions
# ---------------------------------------------------------------------------

class UserFunction:
    """A function typed by the user, e.g. ``M(x) := w*x*(L-x)/2``."""

    def __init__(self, name: str, params: list[str], source: str, workspace: "Workspace"):
        self.name = name
        self.params = params
        self.source = source
        self.workspace = workspace
        self.code, self.tree = compile_expression(source)

    def __call__(self, *args):
        if len(args) != len(self.params):
            raise TypeError(f"{self.name}() takes {len(self.params)} argument(s), got {len(args)}")
        namespace = self.workspace.namespace()
        namespace.update(dict(zip(self.params, args)))
        self.workspace.resolve_units(self.code, namespace)
        return evaluate_code(self.code, namespace)

    def signature(self) -> str:
        return f"{self.name}({', '.join(self.params)})"

    def __repr__(self) -> str:
        return f"{self.signature()} := {self.source}"


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

@dataclass
class VariableInfo:
    name: str
    value: Any
    source: str = ""          # human readable origin, e.g. "Page 1 · Loads"
    expression: str = ""
    order: int = 0


class Workspace:
    """Shared symbol table for every math region and table in a document."""

    def __init__(self):
        self.variables: dict[str, VariableInfo] = {}
        self.functions: dict[str, UserFunction] = {}
        self._base: dict[str, Any] = {}
        self._counter = 0
        self._unit_cache: dict[str, Any] = {}
        # Names defined so far during the current evaluation pass, in document
        # order.  A plain "=" means "define" the first time a name appears and
        # "evaluate" afterwards, and that has to be decided from reading order
        # rather than from whatever a previous pass happened to leave behind.
        self.pass_defined: set[str] = set()
        # Every name the document assigns anywhere.  A name the author defines
        # is theirs, so it is never quietly resolved as a unit just because it
        # is used before the line that defines it.
        self.document_names: set[str] = set()
        self.parent: Optional["Workspace"] = None
        self.rebuild_base()

    def begin_pass(self) -> None:
        self.pass_defined = set()

    def child(self) -> "Workspace":
        """A scope that can read this workspace but keeps its own definitions.

        A multi-line calculation block evaluates in one of these, so the working
        values inside it — a dozen intermediate names — stay inside it instead of
        colliding with the rest of the document.  Anything already defined above
        the block is visible from within it.
        """
        scope = Workspace.__new__(Workspace)
        scope.variables = dict(self.variables)
        scope.functions = dict(self.functions)
        scope._base = self._base
        scope._counter = self._counter
        scope._unit_cache = self._unit_cache
        scope.pass_defined = set(self.pass_defined)
        scope.document_names = self.document_names
        scope.parent = self
        return scope

    def defined_earlier(self, name: str) -> bool:
        return name in self.pass_defined

    # -- namespace ---------------------------------------------------------
    def rebuild_base(self) -> None:
        self._base = {}
        self._base.update(fnlib.CONSTANTS)
        for name, fn in fnlib.FUNCTIONS.items():
            if not keyword.iskeyword(name):
                self._base[name] = fn
        # Keyword-clashing names get an underscore alias too.
        self._base["if_"] = fnlib.if_
        self._base["and_"] = fnlib.and_
        self._base["or_"] = fnlib.or_
        self._base["not_"] = fnlib.not_
        self._base["_lazy_if"] = _lazy_if
        self._base["_lazy_iferror"] = _lazy_iferror

    def namespace(self) -> dict[str, Any]:
        ns = dict(self._base)
        ns.update({name: info.value for name, info in self.variables.items()})
        ns.update(self.functions)
        return ns

    def resolve_units(self, code, namespace: dict[str, Any]) -> None:
        """Bind any still-unknown name in *code* to a unit, if one exists."""
        for name in _all_names(code):
            if name in namespace or name.startswith("__"):
                continue
            if name in self.document_names or name in SHADOWED_UNITS:
                continue        # the author's name, not a unit
            if name in self._unit_cache:
                value = self._unit_cache[name]
                if value is not None:
                    namespace[name] = value
                continue
            try:
                value = Q_(1.0, ureg.Unit(name))
            except Exception:
                value = None
            self._unit_cache[name] = value
            if value is not None:
                namespace[name] = value

    # -- mutation ----------------------------------------------------------
    def clear(self) -> None:
        self.variables.clear()
        self.functions.clear()
        self.pass_defined = set()
        self._counter = 0

    def declare(self, names) -> None:
        """Record every name the document assigns, before anything is evaluated."""
        self.document_names = set(names)

    def define(self, name: str, value: Any, source: str = "", expression: str = "") -> None:
        self._counter += 1
        self.variables[name] = VariableInfo(name, value, source, expression, self._counter)
        self.pass_defined.add(name)

    def define_function(self, name: str, params: list[str], source: str) -> UserFunction:
        fn = UserFunction(name, params, source, self)
        self.functions[name] = fn
        self.pass_defined.add(name)
        return fn

    def get(self, name: str, default: Any = None) -> Any:
        info = self.variables.get(name)
        return info.value if info else default

    def has(self, name: str) -> bool:
        return name in self.variables or name in self.functions

    # -- evaluation --------------------------------------------------------
    def evaluate(self, source: str) -> Any:
        code, _tree = compile_expression(source)
        namespace = self.namespace()
        self.resolve_units(code, namespace)
        return evaluate_code(code, namespace)

    def dependencies(self, source: str) -> set[str]:
        try:
            code, _ = compile_expression(source)
        except Exception:
            return set()
        return {n for n in _all_names(code) if n in self.variables or n in self.functions}


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

DEFINE = "define"
FUNCTION = "function"
EVALUATE = "evaluate"
COMMENT = "comment"
BLANK = "blank"
ERROR = "error"

# An angle the author wrote themselves keeps the unit they chose; an angle that
# fell out of inverse trigonometry is shown in degrees.
_ANGLE_UNIT_RE = re.compile(r"\b(rad|radian|radians|deg|degree|degrees|grad|gradian)\b")

_FUNC_LHS = re.compile(r"^\s*([A-Za-z_Ͱ-Ͽ][\wͰ-Ͽ]*)\s*\(([^()]*)\)\s*$")
_NAME_LHS = re.compile(r"^\s*([A-Za-z_Ͱ-Ͽ][\wͰ-Ͽ]*)\s*$")


@dataclass
class Statement:
    """One parsed line of a math region, with its evaluation outcome."""

    raw: str
    kind: str = EVALUATE
    name: str = ""
    params: list[str] = field(default_factory=list)
    expression: str = ""
    target_unit: str = ""
    comment: str = ""
    result: Any = None
    error: str = ""
    tree: Optional[ast.AST] = None
    forced: bool = True          # written with ":=" or ":" rather than a bare "="
    auto_unit: bool = True       # let the engine pick a readable display unit
    is_input: bool = False       # a value typed out in full, e.g. "896 cm^3"

    @property
    def ok(self) -> bool:
        return not self.error

    def display_unit(self) -> Optional[str]:
        """The unit this result should be shown in."""
        if self.target_unit:
            return self.target_unit
        if not self.auto_unit:
            return None
        unit = preferred_unit(self.result)
        if unit == "deg" and _ANGLE_UNIT_RE.search(self.expression):
            return None          # the author picked an angle unit; respect it
        if unit and self.is_input and reads_well(self.result):
            return None          # "896 cm³" was typed that way on purpose
        return unit

    def result_text(self, digits: int = 4, mode: str = "auto") -> str:
        if self.error:
            return ""
        return format_quantity(self.result, digits, mode, self.display_unit())


def parse_statement(line: str) -> Statement:
    """Parse a single source line into a :class:`Statement` (no evaluation)."""
    raw = line.rstrip()
    text = normalise(raw).strip()
    if not text:
        return Statement(raw=raw, kind=BLANK)
    if text.startswith("#") or text.startswith("//"):
        return Statement(raw=raw, kind=COMMENT, comment=text.lstrip("#/ ").rstrip())

    # trailing inline comment
    inline = _split_top_level(text, "#")
    comment = ""
    if inline and inline[0].strip():
        text, comment = inline[0].strip(), inline[1].strip()

    # display-unit conversion suffix
    target_unit = ""
    for arrow in _ARROWS:
        split = _split_top_level(text, arrow)
        if split and split[0].strip():
            text, target_unit = split[0].strip(), split[1].strip()
            break

    # A definition can be written three ways.  ":=" and a bare ":" always
    # define, even over a name that already exists.  A plain "=" defines the
    # first time the name is seen and evaluates afterwards, which is decided
    # later, once reading order is known.
    forced = True
    parts = _split_top_level(text, ":=")
    if parts is None:
        colon = _split_top_level(text, ":")
        if colon and colon[0].strip() and colon[1].strip():
            parts = colon
    if parts is None:
        equals = _split_top_level(text, "=")
        # a comparison operator is not an assignment
        if (equals and not equals[0].rstrip().endswith(("<", ">", "!", "="))
                and not equals[1].startswith("=")):
            parts = equals
            forced = False
    if parts is not None:
        lhs, rhs = parts[0].strip(), parts[1].strip()
        if not rhs:
            # "expr =" is an evaluation request
            return Statement(raw=raw, kind=EVALUATE, expression=lhs,
                             target_unit=target_unit, comment=comment)
        func = _FUNC_LHS.match(lhs)
        if func:
            params = [p.strip() for p in func.group(2).split(",") if p.strip()]
            return Statement(raw=raw, kind=FUNCTION, name=func.group(1), params=params,
                             expression=rhs, target_unit=target_unit, comment=comment,
                             forced=forced)
        name = _NAME_LHS.match(lhs)
        if name:
            return Statement(raw=raw, kind=DEFINE, name=name.group(1), expression=rhs,
                             target_unit=target_unit, comment=comment, forced=forced)
        if forced:
            return Statement(raw=raw, kind=ERROR, expression=text,
                             error=f"'{lhs}' is not a valid name to define")

    return Statement(raw=raw, kind=EVALUATE, expression=text,
                     target_unit=target_unit, comment=comment)


def evaluate_statement(statement: Statement, workspace: Workspace, source: str = "") -> Statement:
    """Evaluate a parsed statement against *workspace*, storing results in place."""
    statement.result = None
    statement.error = ""
    if statement.kind in (BLANK, COMMENT, ERROR):
        return statement

    # A plain "=" over a name that an earlier line already defined is a check,
    # not a redefinition — write ":=" or ":" to assign again.
    if (statement.kind in (DEFINE, FUNCTION) and not statement.forced
            and workspace.defined_earlier(statement.name)):
        statement.kind = EVALUATE
        statement.expression = f"({statement.name}) == ({statement.expression})"

    try:
        if statement.kind == FUNCTION:
            fn = workspace.define_function(statement.name, statement.params, statement.expression)
            statement.tree = fn.tree
            statement.result = fn
            return statement

        code, tree = compile_expression(statement.expression)
        statement.tree = tree
        namespace = workspace.namespace()
        workspace.resolve_units(code, namespace)
        value = evaluate_code(code, namespace)

        if statement.target_unit:
            try:
                value = convert(value, statement.target_unit)
            except Exception as exc:
                statement.error = friendly_error(exc)
                return statement
        else:
            value = simplify_units(value)

        statement.result = value
        # Store the value in the unit it reads best in, so the variables panel,
        # spreadsheet cells and exports all agree with what is on the page — but
        # never rewrite a value the author typed out in full.
        statement.is_input = is_unit_literal(tree)
        if not statement.target_unit:
            unit = statement.display_unit()
            if unit:
                try:
                    value = convert(value, unit)
                    statement.result = value
                except Exception:
                    pass
        if statement.kind == DEFINE:
            workspace.define(statement.name, value, source, statement.expression)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as text
        statement.error = friendly_error(exc)
    return statement


def evaluate_source(text: str, workspace: Workspace, source: str = "",
                    new_pass: bool = True) -> list[Statement]:
    """Parse and evaluate a whole math region, top to bottom.

    *new_pass* resets the record of which names have been defined so far.  A
    document evaluates many regions in reading order within one pass, so it
    resets once at the start and passes ``new_pass=False`` for each region.
    """
    if new_pass:
        workspace.begin_pass()
    statements = []
    for line in text.split("\n"):
        statement = parse_statement(line)
        evaluate_statement(statement, workspace, source)
        statements.append(statement)
    return statements
