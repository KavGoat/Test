"""Built-in function library for the calculation engine."""
from __future__ import annotations

import math
from typing import Any, Callable, Optional

import numpy as np
import sympy

from .units import Quantity, make_quantity, Q_, Unit


def _unwrap(q: Quantity) -> float:
    return q.value if q.dimensionless else q.pint_qty.to_base_units().magnitude


def _wrap(val: float, unit: Optional[Any] = None) -> Quantity:
    if unit is None:
        return Quantity(val)
    return Quantity(val, unit)


FUNCTIONS: dict[str, tuple[Callable, int, str]] = {}


def register(name: str, nargs: int, doc: str = ""):
    def decorator(fn: Callable):
        FUNCTIONS[name] = (fn, nargs, doc)
        return fn
    return decorator


@register("sqrt", 1, "Square root")
def fn_sqrt(x: Quantity) -> Quantity:
    from .units import power_quantity
    return power_quantity(x, 0.5)


@register("root", 2, "Nth root: root(x, n)")
def fn_root(x: Quantity, n: Quantity) -> Quantity:
    from .units import power_quantity
    return power_quantity(x, 1.0 / n.value)


@register("abs", 1, "Absolute value")
def fn_abs(x: Quantity) -> Quantity:
    return Quantity(abs(x.value), x.unit, x.display_unit, x.user_specified_unit)


@register("exp", 1, "Exponential e^x")
def fn_exp(x: Quantity) -> Quantity:
    return Quantity(math.exp(x.value))


@register("ln", 1, "Natural logarithm")
def fn_ln(x: Quantity) -> Quantity:
    return Quantity(math.log(_unwrap(x)))


@register("log", 1, "Base-10 logarithm")
def fn_log(x: Quantity) -> Quantity:
    return Quantity(math.log10(_unwrap(x)))


@register("sin", 1, "Sine (degrees or radians)")
def fn_sin(x: Quantity) -> Quantity:
    v = x.value
    if x.unit and str(x.unit) == "degree":
        v = math.radians(v)
    return Quantity(math.sin(v))


@register("cos", 1, "Cosine")
def fn_cos(x: Quantity) -> Quantity:
    v = x.value
    if x.unit and str(x.unit) == "degree":
        v = math.radians(v)
    return Quantity(math.cos(v))


@register("tan", 1, "Tangent")
def fn_tan(x: Quantity) -> Quantity:
    v = x.value
    if x.unit and str(x.unit) == "degree":
        v = math.radians(v)
    return Quantity(math.tan(v))


@register("asin", 1, "Arcsine (returns degrees)")
def fn_asin(x: Quantity) -> Quantity:
    return Quantity(math.degrees(math.asin(x.value)), Unit("degree"), Unit("degree"))


@register("acos", 1, "Arccosine (returns degrees)")
def fn_acos(x: Quantity) -> Quantity:
    return Quantity(math.degrees(math.acos(x.value)), Unit("degree"), Unit("degree"))


@register("atan", 1, "Arctangent (returns degrees)")
def fn_atan(x: Quantity) -> Quantity:
    return Quantity(math.degrees(math.atan(x.value)), Unit("degree"), Unit("degree"))


@register("atan2", 2, "Two-argument arctangent")
def fn_atan2(y: Quantity, x: Quantity) -> Quantity:
    return Quantity(math.degrees(math.atan2(y.value, x.value)), Unit("degree"), Unit("degree"))


@register("max", -1, "Maximum of arguments")
def fn_max(*args: Quantity) -> Quantity:
    best = args[0]
    for a in args[1:]:
        if a.value > best.value:
            best = a
    return best


@register("min", -1, "Minimum of arguments")
def fn_min(*args: Quantity) -> Quantity:
    best = args[0]
    for a in args[1:]:
        if a.value < best.value:
            best = a
    return best


@register("sum", -1, "Sum of arguments")
def fn_sum(*args: Quantity) -> Quantity:
    from .units import add_quantities
    result = args[0]
    for a in args[1:]:
        result = add_quantities(result, a)
    return result


@register("mean", -1, "Arithmetic mean")
def fn_mean(*args: Quantity) -> Quantity:
    s = fn_sum(*args)
    return Quantity(s.value / len(args), s.unit, s.display_unit)


@register("median", -1, "Median value")
def fn_median(*args: Quantity) -> Quantity:
    vals = sorted(args, key=lambda q: q.value)
    n = len(vals)
    if n % 2 == 1:
        return vals[n // 2]
    a, b = vals[n // 2 - 1], vals[n // 2]
    return Quantity((a.value + b.value) / 2, a.unit, a.display_unit)


@register("stdev", -1, "Standard deviation")
def fn_stdev(*args: Quantity) -> Quantity:
    vals = [a.value for a in args]
    m = sum(vals) / len(vals)
    variance = sum((v - m) ** 2 for v in vals) / len(vals)
    return Quantity(math.sqrt(variance), args[0].unit, args[0].display_unit)


@register("round", 2, "Round to n decimal places")
def fn_round(x: Quantity, n: Quantity) -> Quantity:
    return Quantity(round(x.value, int(n.value)), x.unit, x.display_unit, x.user_specified_unit)


@register("ceil", 1, "Ceiling")
def fn_ceil(x: Quantity) -> Quantity:
    return Quantity(math.ceil(x.value), x.unit, x.display_unit, x.user_specified_unit)


@register("floor", 1, "Floor")
def fn_floor(x: Quantity) -> Quantity:
    return Quantity(math.floor(x.value), x.unit, x.display_unit, x.user_specified_unit)


@register("if", 3, "Conditional: if(cond, then, else)")
def fn_if(cond: Quantity, then: Quantity, else_: Quantity) -> Quantity:
    return then if cond.value else else_


@register("and", 2, "Logical AND")
def fn_and(a: Quantity, b: Quantity) -> Quantity:
    return Quantity(1.0 if (a.value and b.value) else 0.0)


@register("or", 2, "Logical OR")
def fn_or(a: Quantity, b: Quantity) -> Quantity:
    return Quantity(1.0 if (a.value or b.value) else 0.0)


@register("not", 1, "Logical NOT")
def fn_not(x: Quantity) -> Quantity:
    return Quantity(0.0 if x.value else 1.0)


@register("det", 1, "Matrix determinant")
def fn_det(x: Quantity) -> Quantity:
    if isinstance(x.value, np.ndarray):
        return Quantity(float(np.linalg.det(x.value)))
    return Quantity(x.value)


@register("inv", 1, "Matrix inverse")
def fn_inv(x: Quantity) -> Quantity:
    if isinstance(x.value, np.ndarray):
        return Quantity(np.linalg.inv(x.value))
    return Quantity(1.0 / x.value)


@register("norm", 1, "Vector/matrix norm")
def fn_norm(x: Quantity) -> Quantity:
    if isinstance(x.value, np.ndarray):
        return Quantity(float(np.linalg.norm(x.value)))
    return Quantity(abs(x.value))


@register("interp", 3, "Linear interpolation: interp(x, xs, ys)")
def fn_interp(x: Quantity, xs: Quantity, ys: Quantity) -> Quantity:
    return Quantity(float(np.interp(x.value, xs.value, ys.value)))


@register("diff", 2, "Numerical derivative: diff(f, x)")
def fn_diff(f_val: Quantity, x: Quantity) -> Quantity:
    return Quantity(f_val.value)


@register("pi", 0, "Pi constant")
def fn_pi() -> Quantity:
    return Quantity(math.pi)


@register("e", 0, "Euler's number")
def fn_e() -> Quantity:
    return Quantity(math.e)


@register("mag", 1, "Magnitude (strip units)")
def fn_mag(x: Quantity) -> Quantity:
    return Quantity(x.value)


@register("unit_of", 1, "Get unit of quantity as 1*unit")
def fn_unit_of(x: Quantity) -> Quantity:
    if x.unit is None:
        return Quantity(1.0)
    return Quantity(1.0, x.unit, x.display_unit)


def get_function(name: str) -> Optional[tuple[Callable, int, str]]:
    return FUNCTIONS.get(name)


def list_functions() -> list[tuple[str, str]]:
    return [(name, info[2]) for name, info in sorted(FUNCTIONS.items())]
