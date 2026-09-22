"""Plot renderer for SMath Studio -- generates matplotlib plots as PIL Images."""

from __future__ import annotations

import math
from typing import Any, Optional, TYPE_CHECKING

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from PIL import Image
import io

if TYPE_CHECKING:
    from ..parser import PlotRegion
    from ..context import EvalContext
    from ..expression import ASTNode


# ---------------------------------------------------------------------------
# Expression-to-callable conversion
# ---------------------------------------------------------------------------

def _ast_to_label(node: "ASTNode") -> str:
    """Best-effort conversion of an AST node to a human-readable label."""
    from ..expression import (
        Number, Variable, FunctionCall, BinaryOp, UnaryOp, Evaluation,
    )

    if isinstance(node, Evaluation):
        return _ast_to_label(node.expression)
    if isinstance(node, Number):
        return str(node.value)
    if isinstance(node, Variable):
        return node.name
    if isinstance(node, FunctionCall):
        inner = ", ".join(_ast_to_label(a) for a in node.args)
        return f"{node.name}({inner})"
    if isinstance(node, BinaryOp):
        left = _ast_to_label(node.left)
        right = _ast_to_label(node.right)
        return f"{left} {node.operator} {right}"
    if isinstance(node, UnaryOp):
        return f"{node.operator}{_ast_to_label(node.operand)}"
    return repr(node)


def _try_build_callable(
    expr: "ASTNode", ctx: "EvalContext"
) -> Optional[callable]:
    """Try to build a callable f(x) -> y from an AST expression.

    The strategy: set x in the context, evaluate the expression, and check
    that the result is numeric. If it works, return a closure that does this
    for each x value.
    """
    from ..expression import Variable

    # We evaluate the expression with 'x' bound to each sample value.
    # First, do a quick smoke-test with x=1.0 to see if it produces a number.
    original_x = ctx.get_variable("x")
    try:
        ctx.set_variable("x", 1.0)
        test_val = expr.evaluate(ctx)
        if not isinstance(test_val, (int, float)):
            # Check if it's a Quantity (has .value)
            if hasattr(test_val, "value") and isinstance(test_val.value, (int, float)):
                pass  # OK, we can extract .value
            else:
                return None
    except Exception:
        return None
    finally:
        # Restore original x
        if original_x is not None:
            ctx.set_variable("x", original_x)
        else:
            ctx.set_variable("x", None)

    def _evaluate_at(x_val: float) -> Optional[float]:
        ctx.set_variable("x", x_val)
        try:
            result = expr.evaluate(ctx)
            if isinstance(result, (int, float)):
                return float(result)
            if hasattr(result, "value") and isinstance(result.value, (int, float)):
                return float(result.value)
            return None
        except Exception:
            return None

    return _evaluate_at


def _unwrap_evaluation(node: "ASTNode") -> "ASTNode":
    """Unwrap Evaluation nodes to get the inner expression."""
    from ..expression import Evaluation
    while isinstance(node, Evaluation):
        node = node.expression
    return node


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_plot(
    plot: "PlotRegion",
    ctx: "EvalContext",
    width: int = 400,
    height: int = 300,
    dpi: int = 100,
) -> Image.Image:
    """Render a PlotRegion to a PIL Image using matplotlib.

    Parameters
    ----------
    plot : PlotRegion
        The plot region data from the parser.
    ctx : EvalContext
        The evaluation context (variables, functions, constants).
    width, height : int
        Desired pixel dimensions for the output image.
    dpi : int
        Resolution for the matplotlib figure.

    Returns
    -------
    PIL.Image.Image
        The rendered plot as an RGBA PIL Image.
    """
    fig_w = width / dpi
    fig_h = height / dpi

    fig = Figure(figsize=(fig_w, fig_h), dpi=dpi, facecolor="white")
    ax = fig.add_subplot(111)

    ax.set_facecolor("white")
    ax.grid(True, linewidth=0.5, alpha=0.3, color="#c0c0c0", linestyle="-")
    ax.tick_params(labelsize=7, direction="in", length=3, width=0.5, colors="#444")
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
        spine.set_color("#666666")

    expr_label = ""
    plotted = False
    colors = ["#0000cc", "#cc0000", "#008800", "#cc6600", "#8800cc"]
    color_idx = 0

    if plot.input_expr is not None:
        inner_expr = _unwrap_evaluation(plot.input_expr)
        expr_label = _ast_to_label(inner_expr)

        func = _try_build_callable(inner_expr, ctx)
        if func is not None:
            x_min = float(plot.attributes.get("x_min", -10))
            x_max = float(plot.attributes.get("x_max", 10))
            num_points = 500

            xs = np.linspace(x_min, x_max, num_points)
            ys = []
            for xv in xs:
                yv = func(float(xv))
                ys.append(yv if yv is not None else float("nan"))

            ys_arr = np.array(ys, dtype=float)

            valid_mask = np.isfinite(ys_arr)
            if np.any(valid_mask):
                ax.plot(xs, ys_arr, color=colors[color_idx % len(colors)],
                        linewidth=1.2, antialiased=True)
                plotted = True

    ax.set_xlabel("x", fontsize=7, color="#444")
    ax.set_ylabel("y", fontsize=7, color="#444")

    if not plotted:
        ax.text(
            0.5, 0.5, "(no data)",
            transform=ax.transAxes,
            ha="center", va="center",
            fontsize=9, color="#999999", style="italic",
        )

    fig.tight_layout(pad=1.2)

    # Render to PIL Image
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="white")
    buf.seek(0)
    img = Image.open(buf).copy()  # .copy() so we can close the buffer
    buf.close()
    plt.close(fig)

    return img
