"""symbolic(expression[, "expand" | "factor"]): the one symbolic function.

Everything else in the worksheet is numeric.  Inside symbolic(...), letters
without a value stay letters and diff, int, sum, product, solve and lim give
formulas (through SymPy, see sym.py).  The answer is a formula while it
holds letters, otherwise the number.  It is never guessed: what SymPy cannot
do exactly is an error.  (Not an SMath function: EXTRA_FUNCTIONS names it so
the SMath autocomplete checks leave it out.)"""
from __future__ import annotations

from . import ast as A
from .builtins import SPECIAL
from .catalog import FUNCTIONS
from .errors import SMathError, err
from .values import String

EXTRA_FUNCTIONS = {"symbolic"}

CANNOT = "This expression cannot be evaluated symbolically."
NO_LIMIT = "The limit does not exist or cannot be determined."

FUNCTIONS.append(("symbolic", -1, "Unknown",
                  'symbolic("1:expression") — Evaluates "1:expression" symbolically: letters without a value '
                  "stay letters, and diff, int, sum, product, solve and lim inside give formulas. "
                  'symbolic("1:expression", "2:mode") with "expand" or "factor" multiplies out or factorises.'))


def _symbolic(ev, n: A.Call, ctx):
    from . import sym
    from .symbolic import Expr, NotSymbolic

    if len(n.args) not in (1, 2):
        raise err("args_count", node=n)
    mode = "simplify"
    if len(n.args) == 2:
        m = ev.eval(n.args[1], ctx)
        if not isinstance(m, String) or m.text not in sym.MODES:
            raise SMathError('The mode must be "expand", "factor" or "simplify".', n.args[1])
        mode = m.text
    try:
        e = sym.symbolic(n.args[0], ctx, ev, mode)
        node = sym.from_sympy(e)
    except sym.NoLimit:
        raise SMathError(NO_LIMIT, n) from None
    except sym.NoSolution:
        raise err("no_solution", node=n) from None
    except NotSymbolic:
        raise SMathError(CANNOT, n) from None
    if sym.is_formula(e):
        return Expr(node)
    from .evaluator import Context

    # no letters left: the number (with its units); a fresh context so a
    # worksheet redefinition of e or π cannot change the constants
    return ev.eval(node, Context())


SPECIAL["symbolic"] = _symbolic
