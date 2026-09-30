"""Number formatting exactly as SMath shows results.

Observed on SMath Cloud with the default worksheet settings
(decimal places 4, exponential threshold 5, trailing zeros off):

    1/3        -> 0.3333          123456      -> 1.2346·10^5
    10/4       -> 2.5             99999       -> 99999
    1.50       -> 1.5             1234567.8   -> 1.2346·10^6
    0.001234   -> 0.0012          0.00001234  -> 1.234·10^-5
    1/7000     -> 0.0001          100000.5    -> 1·10^5

A number is written in exponential form when its decimal exponent is at
least the threshold (or at most minus the threshold); otherwise it is rounded
to the given number of decimal places.  "Significant figures mode" rounds to
that many significant digits instead.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext


@dataclass
class NumberFormat:
    decimals: int = 4
    threshold: int = 5
    trailing_zeros: bool = False
    significant: bool = False
    # SMath's "Rounding" option: "Half to even" is the default (observed:
    # checked in the right-click menu). Like SMath, the binary value itself
    # is rounded, so 2.00025 (really 2.000249999...) shows 2.0002.
    half_even: bool = True
    fractions: str = "decimal"  # "decimal", "fraction" or "auto" (right-click > Fractions)
    mixed: bool = False  # "Use mixed numbers": 7/3 -> 2 1/3
    # engineering output units: 12500 N -> 12.5 kN, 2.5e8 Pa -> 250 MPa,
    # 6.667e-5 m^4 -> 6.6667e7 mm^4 (not SMath's own behaviour; Tools > Options)
    engineering: bool = True


@dataclass(frozen=True)
class FormattedNumber:
    """mantissa text, optional power of ten, sign handled separately."""

    negative: bool
    mantissa: str
    exponent: int | None = None

    def plain(self) -> str:
        s = ("-" if self.negative else "") + self.mantissa
        if self.exponent is not None:
            s += f"·10^{self.exponent}"
        return s


def _round(x, places: int, fmt: NumberFormat) -> str:
    mode = ROUND_HALF_EVEN if fmt.half_even else ROUND_HALF_UP
    q = Decimal(1).scaleb(-places) if places > 0 else Decimal(1)
    with localcontext() as ctx:
        ctx.prec = 400  # 170! has 307 digits before the point
        d = Decimal(x).quantize(q, rounding=mode)
    s = format(d, "f")
    if not fmt.trailing_zeros and "." in s:
        s = s.rstrip("0").rstrip(".")
    elif fmt.trailing_zeros and places > 0 and "." not in s:
        s += "." + "0" * places
    return s


def format_real(x: float, fmt: NumberFormat | None = None) -> FormattedNumber:
    fmt = fmt or NumberFormat()
    if math.isnan(x):
        return FormattedNumber(False, "NaN")
    if math.isinf(x):
        return FormattedNumber(x < 0, "∞")
    neg = x < 0
    a = abs(x)
    if a == 0:
        return FormattedNumber(False, "0" if not fmt.trailing_zeros else "0." + "0" * fmt.decimals)

    # all in exact decimals: the binary value itself, its power of ten and
    # its mantissa (a float division such as 6567.5/1000 = 6.567499... would
    # round an exact tie the wrong way)
    da = Decimal(a)
    exp = da.adjusted()
    # rounding can carry into the next decade (99999.99 -> 100000)
    if fmt.significant:
        places = max(fmt.decimals - 1 - exp, 0)
    else:
        places = fmt.decimals
    fixed = _round(da, places, fmt)
    if Decimal(fixed) != 0:
        exp = Decimal(fixed).adjusted()

    if exp >= fmt.threshold or exp <= -fmt.threshold:
        m = da.scaleb(-exp)
        mplaces = fmt.decimals - 1 if fmt.significant else fmt.decimals
        ms = _round(m, mplaces, fmt)
        if Decimal(ms) >= 10:
            exp += 1
            ms = _round(m.scaleb(-1), mplaces, fmt)
        return FormattedNumber(neg, ms, exp)

    if Decimal(fixed) == 0:
        return FormattedNumber(False, fixed)
    return FormattedNumber(neg, fixed)


def format_plain(x: float, fmt: NumberFormat | None = None) -> str:
    return format_real(x, fmt).plain()
