"""The rest of Excel's worksheet functions (2026-10-10): number bases and
bits, complex numbers, Bessel and error functions, the statistical
distributions and tests, regression (LINEST, LOGEST, GROWTH), the database
functions, depreciation and the remaining money functions, and a few text,
array and information functions.

Written from Excel's documentation; the distributions use mpmath (installed
with sympy). Registered into ``functions.FUNCTIONS`` on import.
"""
from __future__ import annotations

import math
import re
import statistics
import unicodedata
import urllib.parse

import mpmath

from .evaluate import MISSING, RefValue, ev
from .functions import (_OMITTED, CALC, DIV0, FUNCTIONS, NA, NUM, VALUE, Array, ErrorValue, SheetError, criterion,
                        every_value, flag, fn, grid, integer, is_number, magnitude, num, numbers, one,
                        real, rebuild, text, to_float, unify)
from .values import BLANK, general_number, to_text


def _opt_real(v, default):
    return default if v is MISSING else real(v)


def _opt_int(v, default):
    return default if v is MISSING else integer(v)


def _floats(args, a_variant=False):
    return [to_float(x) for x in numbers(args, text_counts=a_variant, logical_counts=a_variant)]


def _column(values) -> Array:
    return Array(tuple((v,) for v in values))


# -- number bases and bits ----------------------------------------------------------------------
_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@fn("BASE", least=2, most=3, lift=(0, 1, 2))
def BASE(number, radix, min_length=MISSING):
    n, r = real(number), integer(radix)
    width = _opt_int(min_length, 0)
    if n < 0 or n >= 2 ** 53 or not 2 <= r <= 36 or not 0 <= width <= 255:
        return NUM
    n = int(n)
    out = ""
    while n:
        n, d = divmod(n, r)
        out = _DIGITS[d] + out
    return (out or "0").rjust(width, "0")


@fn("DECIMAL", least=2, most=2, lift=(0, 1))
def DECIMAL(value, radix):
    t, r = text(value).strip().upper(), integer(radix)
    if not 2 <= r <= 36 or len(t) > 255:
        return NUM
    try:
        return float(int(t, r)) if t else 0.0
    except ValueError:
        return NUM


# Excel's conversions work in ten digits; a negative is the ten-digit two's complement
_BITS = {2: 10, 8: 30, 16: 40}


def _from_base(value, base: int) -> int:
    v = one(value)
    t = (general_number(v) if is_number(v) and not isinstance(v, bool) else to_text(v)).strip().upper()
    if len(t) > 10 or not t:
        raise SheetError(NUM)
    try:
        n = int(t, base)
    except ValueError:
        raise SheetError(NUM)
    bits = _BITS[base]
    if len(t) == 10 and n >= 2 ** (bits - 1):
        n -= 2 ** bits
    return n


def _to_base(n: int, base: int, places) -> str:
    bits = _BITS[base]
    if not -(2 ** (bits - 1)) <= n < 2 ** (bits - 1):
        raise SheetError(NUM)
    if n < 0:
        return BASE(float(n + 2 ** bits), float(base))
    out = BASE(float(n), float(base))
    if places is not MISSING:
        p = integer(places)
        if p <= 0 or p < len(out):
            raise SheetError(NUM)
        out = out.rjust(p, "0")
    return out


def _decimal_in(value) -> int:
    x = real(value)
    return int(x)                      # Excel truncates


for _src, _sb in (("BIN", 2), ("OCT", 8), ("HEX", 16), ("DEC", 10)):
    for _dst, _db in (("BIN", 2), ("OCT", 8), ("HEX", 16), ("DEC", 10)):
        if _src == _dst:
            continue

        def _make(sb=_sb, db=_db):
            def convert(value, places=MISSING):
                n = _decimal_in(value) if sb == 10 else _from_base(value, sb)
                if db == 10:
                    return float(n)
                return _to_base(n, db, places)
            return convert
        fn(f"{_src}2{_dst}", least=1, most=1 if _db == 10 else 2, lift=(0, 1))(_make())


def _bits_in(v) -> int:
    x = real(v)
    if x < 0 or x != int(x) or x >= 2 ** 48:
        raise SheetError(NUM)
    return int(x)


@fn("BITAND", least=2, most=2, lift=(0, 1))
def BITAND(a, b):
    return float(_bits_in(a) & _bits_in(b))


@fn("BITOR", least=2, most=2, lift=(0, 1))
def BITOR(a, b):
    return float(_bits_in(a) | _bits_in(b))


@fn("BITXOR", least=2, most=2, lift=(0, 1))
def BITXOR(a, b):
    return float(_bits_in(a) ^ _bits_in(b))


def _shift(n, k):
    x, s = _bits_in(n), integer(k)
    if abs(s) > 53:
        raise SheetError(NUM)
    out = x << s if s >= 0 else x >> -s
    if out >= 2 ** 48:
        raise SheetError(NUM)
    return float(out)


@fn("BITLSHIFT", least=2, most=2, lift=(0, 1))
def BITLSHIFT(n, k):
    return _shift(n, k)


@fn("BITRSHIFT", least=2, most=2, lift=(0, 1))
def BITRSHIFT(n, k):
    return _shift(n, -integer(k))


@fn("DELTA", least=1, most=2, lift=(0, 1))
def DELTA(a, b=MISSING):
    return 1.0 if real(a) == _opt_real(b, 0.0) else 0.0


@fn("GESTEP", least=1, most=2, lift=(0, 1))
def GESTEP(n, step=MISSING):
    return 1.0 if real(n) >= _opt_real(step, 0.0) else 0.0


# -- roman numerals ---------------------------------------------------------------------------------
_ROMAN = "MDCLXVI"
_ROMAN_VALUES = (1000, 500, 100, 50, 10, 5, 1)


@fn("ROMAN", least=1, most=2, lift=(0, 1))
def ROMAN(number, form=MISSING):
    """Classic (0) to simplified (4) as Excel writes them: ROMAN(499) is
    CDXCIX, ROMAN(499, 4) is ID."""
    n = real(number)
    if form is MISSING:
        mode = 0
    else:
        f = one(form)
        mode = (0 if f else 4) if isinstance(f, bool) else integer(f)
    if not 0 <= n < 4000 or not 0 <= mode <= 4:
        return VALUE
    value = int(n)
    out = []
    last = len(_ROMAN_VALUES) - 1
    for i in range(last // 2 + 1):
        index = 2 * i
        digit = value // _ROMAN_VALUES[index]
        if digit % 5 == 4:
            index2 = index - 1 if digit == 4 else index - 2
            steps = 0
            while steps < mode and index < last:
                steps += 1
                if _ROMAN_VALUES[index2] - _ROMAN_VALUES[index + 1] <= value:
                    index += 1
                else:
                    steps = mode
            out.append(_ROMAN[index] + _ROMAN[index2])
            value += _ROMAN_VALUES[index] - _ROMAN_VALUES[index2]
        else:
            if digit > 4:
                out.append(_ROMAN[index - 1])
            out.append(_ROMAN[index] * (digit % 5))
            value %= _ROMAN_VALUES[index]
    return "".join(out)


@fn("ARABIC", least=1, most=1, lift=(0,))
def ARABIC(value):
    t = text(value).strip().upper()
    sign = 1
    if t.startswith("-"):
        sign, t = -1, t[1:]
    if len(t) > 255 or any(ch not in _ROMAN for ch in t):
        return VALUE
    worth = dict(zip(_ROMAN, _ROMAN_VALUES))
    total = 0
    for i, ch in enumerate(t):
        v = worth[ch]
        total += -v if i + 1 < len(t) and worth[t[i + 1]] > v else v
    return float(sign * total)


# -- complex numbers ---------------------------------------------------------------------------------
def _complex(v):
    """(complex, suffix) from "3+4i", "-i", "1.5e3-2j", 5 and the like."""
    v = one(v)
    if v is BLANK:
        return 0j, "i"
    if is_number(v) and not isinstance(v, bool):
        return complex(to_float(v)), "i"
    if not isinstance(v, str):
        raise SheetError(VALUE)
    t = v.strip()
    if not t or " " in t:
        raise SheetError(NUM)
    try:
        if t[-1] not in "ij":
            return complex(float(t)), "i"
        body, suffix = t[:-1], t[-1]
        cut = next((i for i in range(len(body) - 1, 0, -1)
                    if body[i] in "+-" and body[i - 1] not in "eE"), 0)
        re_text, im_text = body[:cut], body[cut:]
        im = 1.0 if im_text in ("", "+") else -1.0 if im_text == "-" else float(im_text)
        return complex(float(re_text) if re_text else 0.0, im), suffix
    except ValueError:
        raise SheetError(NUM)


def _number_text(x: float) -> str:
    if x == 0:
        return "0"
    s = format(x, ".15g")
    if "e" in s:
        mant, exp = s.split("e")
        s = f"{mant}E{'-' if exp.startswith('-') else '+'}{exp.lstrip('+-').lstrip('0') or '0'}"
    return s


def _complex_text(z: complex, suffix: str = "i") -> str:
    if not (math.isfinite(z.real) and math.isfinite(z.imag)):
        raise SheetError(NUM)
    a, b = z.real, z.imag
    if abs(a) < 1e-300:
        a = 0.0
    if abs(b) < 1e-300:
        b = 0.0
    if b == 0:
        return _number_text(a)
    coeff = "" if b == 1 else "-" if b == -1 else _number_text(b)
    im = f"{coeff}{suffix}"
    if a == 0:
        return im
    return f"{_number_text(a)}{'' if im.startswith('-') else '+'}{im}"


@fn("COMPLEX", least=2, most=3, lift=(0, 1, 2))
def COMPLEX(re_part, im_part, suffix=MISSING):
    s = "i" if suffix is MISSING else text(suffix)
    if s not in ("i", "j", ""):
        return VALUE
    return _complex_text(complex(real(re_part), real(im_part)), s or "i")


def _complex_fn(name, f, args=1, number_out=False):
    def run(*values):
        zs = [_complex(v) for v in values if v is not MISSING]
        suffixes = {s for z, s in zs if z.imag != 0}
        if len(suffixes) > 1:
            return VALUE
        got = f(*[z for z, _s in zs])
        if number_out:
            return float(got)
        return _complex_text(complex(got), suffixes.pop() if suffixes else "i")
    fn(name, least=args, most=args, lift=tuple(range(args)))(run)


def _cot(z):
    return 1 / mpmath.tan(z)


for _name, _f in (("IMCOS", mpmath.cos), ("IMSIN", mpmath.sin), ("IMTAN", mpmath.tan),
                  ("IMCOSH", mpmath.cosh), ("IMSINH", mpmath.sinh), ("IMCOT", _cot),
                  ("IMSEC", mpmath.sec), ("IMCSC", mpmath.csc), ("IMSECH", mpmath.sech),
                  ("IMCSCH", mpmath.csch), ("IMEXP", mpmath.exp), ("IMLN", mpmath.ln),
                  ("IMLOG10", lambda z: mpmath.log(z, 10)), ("IMLOG2", lambda z: mpmath.log(z, 2)),
                  ("IMSQRT", mpmath.sqrt), ("IMCONJUGATE", lambda z: z.conjugate())):
    _complex_fn(_name, lambda z, f=_f: complex(f(z)))     # ln 0, cot 0…: #NUM!
_complex_fn("IMABS", abs, number_out=True)
_complex_fn("IMREAL", lambda z: z.real, number_out=True)
_complex_fn("IMAGINARY", lambda z: z.imag, number_out=True)
_complex_fn("IMARGUMENT", lambda z: math.atan2(z.imag, z.real) if z != 0 else 1 / 0, number_out=True)
_complex_fn("IMSUB", lambda a, b: a - b, args=2)
_complex_fn("IMDIV", lambda a, b: a / b, args=2)            # by 0: #NUM!


@fn("IMPOWER", least=2, most=2, lift=(0, 1))
def IMPOWER(z, n):
    c, s = _complex(z)
    p = real(n)
    if c == 0:
        return "0" if p > 0 else NUM
    # through the polar form, as Excel does (its last digits included)
    r, theta = abs(c) ** p, math.atan2(c.imag, c.real) * p
    return _complex_text(complex(r * math.cos(theta), r * math.sin(theta)), s)


def _complex_values(args):
    out = []
    for a in args:
        if isinstance(a, (RefValue, Array)):
            out.extend(_complex(v) for v in every_value([a]) if v is not BLANK)
        elif a is not MISSING:
            out.append(_complex(a))
    return out


@fn("IMSUM", least=1)
def IMSUM(*args):
    zs = _complex_values(args)
    if len({s for z, s in zs if z.imag != 0}) > 1:
        return VALUE
    return _complex_text(sum((z for z, _s in zs), 0j), next((s for z, s in zs if z.imag), "i"))


@fn("IMPRODUCT", least=1)
def IMPRODUCT(*args):
    zs = _complex_values(args)
    if len({s for z, s in zs if z.imag != 0}) > 1:
        return VALUE
    total = 1 + 0j
    for z, _s in zs:
        total *= z
    return _complex_text(total, next((s for z, s in zs if z.imag), "i"))


# -- Bessel, error and gamma functions --------------------------------------------------------------
def _bessel(f, x, n, positive=False):
    v, k = real(x), integer(n)
    if k < 0 or (positive and v <= 0):
        return NUM
    return float(f(k, v))


@fn("BESSELJ", least=2, most=2, lift=(0, 1))
def BESSELJ(x, n):
    return _bessel(mpmath.besselj, x, n)


@fn("BESSELY", least=2, most=2, lift=(0, 1))
def BESSELY(x, n):
    return _bessel(mpmath.bessely, x, n, True)


@fn("BESSELI", least=2, most=2, lift=(0, 1))
def BESSELI(x, n):
    return _bessel(mpmath.besseli, x, n)


@fn("BESSELK", least=2, most=2, lift=(0, 1))
def BESSELK(x, n):
    return _bessel(mpmath.besselk, x, n, True)


@fn("ERF", least=1, most=2, lift=(0, 1))
def ERF(lower, upper=MISSING):
    a = real(lower)
    if upper is MISSING:
        return math.erf(a)
    return math.erf(real(upper)) - math.erf(a)


@fn("ERF.PRECISE", least=1, most=1, lift=(0,))
def ERF_PRECISE(x):
    return math.erf(real(x))


@fn("ERFC", "ERFC.PRECISE", least=1, most=1, lift=(0,))
def ERFC(x):
    return math.erfc(real(x))


@fn("GAMMA", least=1, most=1, lift=(0,))
def GAMMA(x):
    v = real(x)
    if v <= 0 and v == int(v):
        return NUM
    return math.gamma(v)


@fn("GAMMALN", "GAMMALN.PRECISE", least=1, most=1, lift=(0,))
def GAMMALN(x):
    v = real(x)
    if v <= 0:
        return NUM
    return math.lgamma(v)


# -- distributions -----------------------------------------------------------------------------------
def _inverse(cdf, p, lo, hi):
    """x where cdf(x) = p, by bisection (cdf rising on [lo, hi])."""
    if not 0 < p < 1:
        raise SheetError(NUM)
    while cdf(hi) < p:
        hi *= 2
        if hi > 1e300:
            raise SheetError(NUM)
    for _ in range(200):
        mid = (lo + hi) / 2
        if cdf(mid) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-15 * max(1.0, abs(mid)):
            break
    return (lo + hi) / 2


def _beta_cdf(x, a, b):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return float(mpmath.betainc(a, b, 0, x, regularized=True))


def _gamma_cdf(x, k, theta=1.0):
    if x <= 0:
        return 0.0
    return float(mpmath.gammainc(k, 0, x / theta, regularized=True))


def _t_cdf(t, df):
    x = df / (df + t * t)
    tail = 0.5 * _beta_cdf(x, df / 2, 0.5)
    return 1 - tail if t > 0 else tail


def _f_cdf(x, d1, d2):
    if x <= 0:
        return 0.0
    return _beta_cdf(d1 * x / (d1 * x + d2), d1 / 2, d2 / 2)


def _norm_cdf(z):
    return 0.5 * math.erfc(-z / math.sqrt(2))


@fn("BETA.DIST", least=4, most=6)
def BETA_DIST(x, alpha, beta, cumulative, a=MISSING, b=MISSING):
    v, al, be = real(x), real(alpha), real(beta)
    lo, hi = _opt_real(a, 0.0), _opt_real(b, 1.0)
    if al <= 0 or be <= 0 or not lo <= v <= hi or lo == hi:
        return NUM
    u = (v - lo) / (hi - lo)
    if flag(cumulative):
        return _beta_cdf(u, al, be)
    if u in (0, 1) and (al < 1 or be < 1):
        return NUM
    return float(u ** (al - 1) * (1 - u) ** (be - 1) / mpmath.beta(al, be)) / (hi - lo)


@fn("BETADIST", least=3, most=5)
def BETADIST(x, alpha, beta, a=MISSING, b=MISSING):
    return BETA_DIST(x, alpha, beta, True, a, b)


@fn("BETA.INV", "BETAINV", least=3, most=5)
def BETA_INV(p, alpha, beta, a=MISSING, b=MISSING):
    q, al, be = real(p), real(alpha), real(beta)
    lo, hi = _opt_real(a, 0.0), _opt_real(b, 1.0)
    if al <= 0 or be <= 0 or lo >= hi or not 0 < q < 1:
        return NUM
    u = _inverse(lambda t: _beta_cdf(t, al, be), q, 0.0, 1.0)
    return lo + u * (hi - lo)


@fn("BINOM.DIST", "BINOMDIST", least=4, most=4)
def BINOM_DIST(k, n, p, cumulative):
    s, t, q = int(real(k)), int(real(n)), real(p)
    if s < 0 or s > t or not 0 <= q <= 1:
        return NUM
    pmf = lambda i: math.comb(t, i) * q ** i * (1 - q) ** (t - i)  # noqa: E731
    return math.fsum(pmf(i) for i in range(s + 1)) if flag(cumulative) else pmf(s)


@fn("BINOM.DIST.RANGE", least=3, most=4)
def BINOM_DIST_RANGE(n, p, s, s2=MISSING):
    t, q, a = int(real(n)), real(p), int(real(s))
    b = a if s2 is MISSING else int(real(s2))
    if not 0 <= q <= 1 or not 0 <= a <= t or not a <= b <= t:
        return NUM
    return math.fsum(math.comb(t, i) * q ** i * (1 - q) ** (t - i) for i in range(a, b + 1))


@fn("BINOM.INV", "CRITBINOM", least=3, most=3)
def BINOM_INV(n, p, alpha):
    t, q, a = int(real(n)), real(p), real(alpha)
    if t < 0 or not 0 <= q <= 1 or not 0 <= a <= 1:
        return NUM
    total = 0.0
    for k in range(t + 1):
        total += math.comb(t, k) * q ** k * (1 - q) ** (t - k)
        if total >= a - 1e-14:
            return float(k)
    return float(t)


@fn("NEGBINOM.DIST", least=4, most=4)
def NEGBINOM_DIST(f, s, p, cumulative):
    k, r, q = int(real(f)), int(real(s)), real(p)
    if k < 0 or r < 1 or not 0 <= q <= 1:
        return NUM
    pmf = lambda i: math.comb(i + r - 1, r - 1) * q ** r * (1 - q) ** i  # noqa: E731
    return math.fsum(pmf(i) for i in range(k + 1)) if flag(cumulative) else pmf(k)


@fn("NEGBINOMDIST", least=3, most=3)
def NEGBINOMDIST(f, s, p):
    return NEGBINOM_DIST(f, s, p, False)


@fn("HYPGEOM.DIST", least=5, most=5)
def HYPGEOM_DIST(sample_s, number_sample, population_s, number_pop, cumulative):
    s, n, m, N = (int(real(v)) for v in (sample_s, number_sample, population_s, number_pop))
    if not (0 <= s <= min(n, m) and 0 < n <= N and 0 < m <= N and s >= n - N + m):
        return NUM
    pmf = lambda i: math.comb(m, i) * math.comb(N - m, n - i) / math.comb(N, n)  # noqa: E731
    if flag(cumulative):
        return math.fsum(pmf(i) for i in range(max(0, n - N + m), s + 1))
    return pmf(s)


@fn("HYPGEOMDIST", least=4, most=4)
def HYPGEOMDIST(sample_s, number_sample, population_s, number_pop):
    return HYPGEOM_DIST(sample_s, number_sample, population_s, number_pop, False)


@fn("POISSON.DIST", "POISSON", least=3, most=3)
def POISSON_DIST(x, mean, cumulative):
    k, lam = int(real(x)), real(mean)
    if k < 0 or lam < 0:
        return NUM
    pmf = lambda i: math.exp(-lam + i * math.log(lam) - math.lgamma(i + 1)) if lam else float(i == 0)  # noqa: E731
    return math.fsum(pmf(i) for i in range(k + 1)) if flag(cumulative) else pmf(k)


@fn("EXPON.DIST", "EXPONDIST", least=3, most=3)
def EXPON_DIST(x, lam, cumulative):
    v, la = real(x), real(lam)
    if v < 0 or la <= 0:
        return NUM
    return 1 - math.exp(-la * v) if flag(cumulative) else la * math.exp(-la * v)


@fn("WEIBULL.DIST", "WEIBULL", least=4, most=4)
def WEIBULL_DIST(x, alpha, beta, cumulative):
    v, a, b = real(x), real(alpha), real(beta)
    if v < 0 or a <= 0 or b <= 0:
        return NUM
    if flag(cumulative):
        return 1 - math.exp(-((v / b) ** a))
    return a / b ** a * v ** (a - 1) * math.exp(-((v / b) ** a))


@fn("GAMMA.DIST", "GAMMADIST", least=4, most=4)
def GAMMA_DIST(x, alpha, beta, cumulative):
    v, a, b = real(x), real(alpha), real(beta)
    if v < 0 or a <= 0 or b <= 0:
        return NUM
    if flag(cumulative):
        return _gamma_cdf(v, a, b)
    if v == 0:
        return NUM if a < 1 else (1 / b if a == 1 else 0.0)
    return math.exp((a - 1) * math.log(v) - v / b - math.lgamma(a) - a * math.log(b))


@fn("GAMMA.INV", "GAMMAINV", least=3, most=3)
def GAMMA_INV(p, alpha, beta):
    q, a, b = real(p), real(alpha), real(beta)
    if a <= 0 or b <= 0 or not 0 <= q < 1:
        return NUM
    if q == 0:
        return 0.0
    return _inverse(lambda t: _gamma_cdf(t, a, b), q, 0.0, max(1.0, a * b * 4))


@fn("LOGNORM.DIST", least=4, most=4)
def LOGNORM_DIST(x, mean, sd, cumulative):
    v, m, s = real(x), real(mean), real(sd)
    if v <= 0 or s <= 0:
        return NUM
    z = (math.log(v) - m) / s
    if flag(cumulative):
        return _norm_cdf(z)
    return math.exp(-z * z / 2) / (v * s * math.sqrt(2 * math.pi))


@fn("LOGNORMDIST", least=3, most=3)
def LOGNORMDIST(x, mean, sd):
    return LOGNORM_DIST(x, mean, sd, True)


@fn("LOGNORM.INV", "LOGINV", least=3, most=3)
def LOGNORM_INV(p, mean, sd):
    q, m, s = real(p), real(mean), real(sd)
    if not 0 < q < 1 or s <= 0:
        return NUM
    return math.exp(m + s * statistics.NormalDist().inv_cdf(q))


@fn("CHISQ.DIST", least=3, most=3)
def CHISQ_DIST(x, df, cumulative):
    v, k = real(x), int(real(df))
    if v < 0 or not 1 <= k <= 10 ** 10:
        return NUM
    if flag(cumulative):
        return _gamma_cdf(v, k / 2, 2.0)
    if v == 0:
        return NUM if k < 2 else (0.5 if k == 2 else 0.0)
    return math.exp((k / 2 - 1) * math.log(v) - v / 2 - math.lgamma(k / 2) - k / 2 * math.log(2))


@fn("CHISQ.DIST.RT", "CHIDIST", least=2, most=2)
def CHISQ_DIST_RT(x, df):
    v, k = real(x), int(real(df))
    if v < 0 or k < 1:
        return NUM
    return float(mpmath.gammainc(k / 2, v / 2, mpmath.inf, regularized=True))


@fn("CHISQ.INV", least=2, most=2)
def CHISQ_INV(p, df):
    q, k = real(p), int(real(df))
    if not 0 <= q < 1 or k < 1:
        return NUM
    return 0.0 if q == 0 else _inverse(lambda t: _gamma_cdf(t, k / 2, 2.0), q, 0.0, max(1.0, 4.0 * k))


@fn("CHISQ.INV.RT", "CHIINV", least=2, most=2)
def CHISQ_INV_RT(p, df):
    q = real(p)
    if not 0 < q <= 1:
        return NUM
    return CHISQ_INV(1 - q, df) if q < 1 else 0.0


@fn("CHISQ.TEST", "CHITEST", least=2, most=2)
def CHISQ_TEST(actual, expected):
    a, e = grid(actual), grid(expected)
    if (a.height, a.width) != (e.height, e.width):
        return NA
    stat = 0.0
    for x, y in zip(a.values(), e.values()):
        if is_number(x) and is_number(y):
            ex = to_float(y)
            if ex == 0:
                return DIV0
            stat += (to_float(x) - ex) ** 2 / ex
    r, c = a.height, a.width
    df = (r - 1) * (c - 1) if r > 1 and c > 1 else max(r, c) - 1
    if df < 1:
        return NA
    return CHISQ_DIST_RT(stat, float(df))


@fn("F.DIST", least=4, most=4)
def F_DIST(x, d1, d2, cumulative):
    v, a, b = real(x), int(real(d1)), int(real(d2))
    if v < 0 or a < 1 or b < 1:
        return NUM
    if flag(cumulative):
        return _f_cdf(v, a, b)
    if v == 0:
        return NUM if a < 2 else (1.0 if a == 2 else 0.0)
    return float(mpmath.sqrt((a * v) ** a * b ** b / (a * v + b) ** (a + b)) / (v * mpmath.beta(a / 2, b / 2)))


@fn("F.DIST.RT", "FDIST", least=3, most=3)
def F_DIST_RT(x, d1, d2):
    v, a, b = real(x), int(real(d1)), int(real(d2))
    if v < 0 or a < 1 or b < 1:
        return NUM
    return _beta_cdf(b / (b + a * v), b / 2, a / 2)


@fn("F.INV", least=3, most=3)
def F_INV(p, d1, d2):
    q, a, b = real(p), int(real(d1)), int(real(d2))
    if not 0 <= q < 1 or a < 1 or b < 1:
        return NUM
    return 0.0 if q == 0 else _inverse(lambda t: _f_cdf(t, a, b), q, 0.0, 10.0)


@fn("F.INV.RT", "FINV", least=3, most=3)
def F_INV_RT(p, d1, d2):
    q = real(p)
    if not 0 < q <= 1:
        return NUM
    return F_INV(1 - q, d1, d2) if q < 1 else 0.0


@fn("F.TEST", "FTEST", least=2, most=2)
def F_TEST(a1, a2):
    x, y = _floats([a1]), _floats([a2])
    if len(x) < 2 or len(y) < 2:
        return DIV0
    vx, vy = statistics.variance(x), statistics.variance(y)
    if vx == 0 or vy == 0:
        return DIV0
    c = _f_cdf(vx / vy, len(x) - 1, len(y) - 1)
    return 2 * min(c, 1 - c)


@fn("T.DIST", least=3, most=3)
def T_DIST(x, df, cumulative):
    v, k = real(x), real(df)
    if k < 1:
        return NUM
    k = int(k)
    if flag(cumulative):
        return _t_cdf(v, k)
    return math.exp(math.lgamma((k + 1) / 2) - math.lgamma(k / 2)) / math.sqrt(k * math.pi) * \
        (1 + v * v / k) ** (-(k + 1) / 2)


@fn("T.DIST.RT", least=2, most=2)
def T_DIST_RT(x, df):
    k = int(real(df))
    if k < 1:
        return NUM
    return 1 - _t_cdf(real(x), k)


@fn("T.DIST.2T", least=2, most=2)
def T_DIST_2T(x, df):
    v, k = real(x), int(real(df))
    if v < 0 or k < 1:
        return NUM
    return 2 * (1 - _t_cdf(v, k))


@fn("TDIST", least=3, most=3)
def TDIST(x, df, tails):
    t = integer(tails)
    if t not in (1, 2) or real(x) < 0:
        return NUM
    return T_DIST_RT(x, df) if t == 1 else T_DIST_2T(x, df)


@fn("T.INV", least=2, most=2)
def T_INV(p, df):
    q, k = real(p), int(real(df))
    if not 0 < q < 1 or k < 1:
        return NUM
    if q == 0.5:
        return 0.0
    if q < 0.5:
        return -T_INV(1 - q, df)
    return _inverse(lambda t: _t_cdf(t, k), q, 0.0, 10.0)


@fn("T.INV.2T", "TINV", least=2, most=2)
def T_INV_2T(p, df):
    q = real(p)
    if not 0 < q <= 1:
        return NUM
    return T_INV(1 - q / 2, df) if q < 1 else 0.0


@fn("T.TEST", "TTEST", least=4, most=4)
def T_TEST(a1, a2, tails, kind):
    t, k = integer(tails), integer(kind)
    if t not in (1, 2) or k not in (1, 2, 3):
        return NUM
    if k == 1:
        ga, gb = list(grid(a1).values()), list(grid(a2).values())
        if len(ga) != len(gb):
            return NA
        d = [to_float(x) - to_float(y) for x, y in zip(ga, gb) if is_number(x) and is_number(y)]
        n = len(d)
        if n < 2:
            return DIV0
        sd = statistics.stdev(d)
        if sd == 0:
            return DIV0
        stat, df = statistics.fmean(d) / (sd / math.sqrt(n)), n - 1
    else:
        x, y = _floats([a1]), _floats([a2])
        nx, ny = len(x), len(y)
        if nx < 2 or ny < 2:
            return DIV0
        vx, vy = statistics.variance(x), statistics.variance(y)
        diff = statistics.fmean(x) - statistics.fmean(y)
        if k == 2:
            pooled = ((nx - 1) * vx + (ny - 1) * vy) / (nx + ny - 2)
            se = math.sqrt(pooled * (1 / nx + 1 / ny))
            df = nx + ny - 2
        else:
            se = math.sqrt(vx / nx + vy / ny)
            df = (vx / nx + vy / ny) ** 2 / ((vx / nx) ** 2 / (nx - 1) + (vy / ny) ** 2 / (ny - 1))
        if se == 0:
            return DIV0
        stat = diff / se
    x = df / (df + stat * stat)
    one_tail = 0.5 * _beta_cdf(x, df / 2, 0.5)
    return one_tail * t


@fn("Z.TEST", "ZTEST", least=2, most=3)
def Z_TEST(array, x, sigma=MISSING):
    data = _floats([array])
    n = len(data)
    if n < 1 or (sigma is MISSING and n < 2):
        return DIV0
    s = statistics.stdev(data) if sigma is MISSING else real(sigma)
    if s == 0:
        return DIV0
    return 1 - _norm_cdf((statistics.fmean(data) - real(x)) / (s / math.sqrt(n)))


@fn("CONFIDENCE.NORM", "CONFIDENCE", least=3, most=3)
def CONFIDENCE_NORM(alpha, sd, size):
    a, s, n = real(alpha), real(sd), int(real(size))
    if not 0 < a < 1 or s <= 0 or n < 1:
        return NUM
    return statistics.NormalDist().inv_cdf(1 - a / 2) * s / math.sqrt(n)


@fn("CONFIDENCE.T", least=3, most=3)
def CONFIDENCE_T(alpha, sd, size):
    a, s, n = real(alpha), real(sd), int(real(size))
    if not 0 < a < 1 or s <= 0 or n < 1:
        return NUM
    if n == 1:
        return DIV0
    return T_INV_2T(a, float(n - 1)) * s / math.sqrt(n)


@fn("PHI", least=1, most=1, lift=(0,))
def PHI(x):
    v = real(x)
    return math.exp(-v * v / 2) / math.sqrt(2 * math.pi)


@fn("GAUSS", least=1, most=1, lift=(0,))
def GAUSS(z):
    return _norm_cdf(real(z)) - 0.5


@fn("FISHER", least=1, most=1, lift=(0,))
def FISHER(x):
    v = real(x)
    if not -1 < v < 1:
        return NUM
    return 0.5 * math.log((1 + v) / (1 - v))


@fn("FISHERINV", least=1, most=1, lift=(0,))
def FISHERINV(y):
    return math.tanh(real(y))


@fn("PROB", least=3, most=4)
def PROB(xs, probs, lower, upper=MISSING):
    gx, gp = list(grid(xs).values()), list(grid(probs).values())
    if len(gx) != len(gp):
        return NA
    p = [to_float(v) for v in gp if is_number(v)]
    if any(not 0 <= v <= 1 for v in p) or abs(math.fsum(p) - 1) > 1e-7:
        return NUM
    lo = real(lower)
    hi = lo if upper is MISSING else real(upper)
    return math.fsum(to_float(q) for x, q in zip(gx, gp)
                     if is_number(x) and is_number(q) and lo <= to_float(x) <= hi)


# -- descriptive statistics --------------------------------------------------------------------------
@fn("KURT", least=1)
def KURT(*args):
    x = _floats(args)
    n = len(x)
    if n < 4:
        return DIV0
    m, s = statistics.fmean(x), statistics.stdev(x)
    if s == 0:
        return DIV0
    k = math.fsum(((v - m) / s) ** 4 for v in x)
    return n * (n + 1) / ((n - 1) * (n - 2) * (n - 3)) * k - 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))


@fn("SKEW", least=1)
def SKEW(*args):
    x = _floats(args)
    n = len(x)
    if n < 3:
        return DIV0
    m, s = statistics.fmean(x), statistics.stdev(x)
    if s == 0:
        return DIV0
    return n / ((n - 1) * (n - 2)) * math.fsum(((v - m) / s) ** 3 for v in x)


@fn("SKEW.P", least=1)
def SKEW_P(*args):
    x = _floats(args)
    n = len(x)
    if n < 1:
        return DIV0
    m, s = statistics.fmean(x), statistics.pstdev(x)
    if s == 0:
        return DIV0
    return math.fsum(((v - m) / s) ** 3 for v in x) / n


def _variance_a(args, sample):
    si, dims, unit = unify(numbers(args, text_counts=True, logical_counts=True))
    n = len(si)
    if n < (2 if sample else 1):
        raise SheetError(DIV0)
    m = math.fsum(si) / n
    return math.fsum((x - m) ** 2 for x in si) / (n - 1 if sample else n), dims, unit


@fn("VARA", least=1)
def VARA(*args):
    v, dims, unit = _variance_a(args, True)
    return rebuild(v, dims, unit, 2.0)


@fn("VARPA", least=1)
def VARPA(*args):
    v, dims, unit = _variance_a(args, False)
    return rebuild(v, dims, unit, 2.0)


@fn("STDEVPA", least=1)
def STDEVPA(*args):
    v, dims, unit = _variance_a(args, False)
    return rebuild(math.sqrt(v), dims, unit)


@fn("TRIMMEAN", least=2, most=2)
def TRIMMEAN(array, percent):
    si, dims, unit = unify(numbers([array]))
    p = real(percent)
    if not 0 <= p < 1 or not si:
        return NUM
    k = int(len(si) * p / 2)               # from each end, rounded down to an even total
    kept = sorted(si)[k:len(si) - k]
    return rebuild(math.fsum(kept) / len(kept), dims, unit)


@fn("MODE.MULT", least=1)
def MODE_MULT(*args):
    si, dims, unit = unify(numbers(args))
    counts: dict = {}
    for x in si:
        counts[x] = counts.get(x, 0) + 1
    best = max(counts.values(), default=0)
    if best < 2:
        return NA
    seen, out = set(), []
    for x in si:
        if counts[x] == best and x not in seen:
            seen.add(x)
            out.append(rebuild(x, dims, unit))
    return _column(out)


def _percentrank(array, x, significance, exclusive):
    data = sorted(_floats([array]))
    v = real(x)
    digits = 3 if significance is MISSING else integer(significance)
    n = len(data)
    if n == 0 or digits < 1 or v < data[0] or v > data[-1]:
        return NA
    if v in data:
        i = data.index(v)
        rank = (i + 1) / (n + 1) if exclusive else (i / (n - 1) if n > 1 else 1.0)
    else:
        j = next(i for i, d in enumerate(data) if d > v) - 1
        frac = (v - data[j]) / (data[j + 1] - data[j])
        rank = ((j + 1 + frac) / (n + 1)) if exclusive else ((j + frac) / (n - 1))
    scale = 10 ** digits
    return math.floor(rank * scale + 1e-9) / scale       # Excel truncates


@fn("PERCENTRANK", "PERCENTRANK.INC", least=2, most=3)
def PERCENTRANK(array, x, significance=MISSING):
    return _percentrank(array, x, significance, False)


@fn("PERCENTRANK.EXC", least=2, most=3)
def PERCENTRANK_EXC(array, x, significance=MISSING):
    return _percentrank(array, x, significance, True)


@fn("RANK.AVG", least=2, most=3)
def RANK_AVG(x, ref, order=MISSING):
    value = magnitude(num(x))
    si, _dims, _unit = unify(numbers([ref]))
    if value not in si:
        return NA
    ordered = sorted(si, reverse=not flag(order))
    first = ordered.index(value) + 1
    return first + (ordered.count(value) - 1) / 2


@fn("FREQUENCY", least=2, most=2)
def FREQUENCY(data, bins):
    xs = _floats([data])
    edges = sorted(_floats([bins]))
    counts = [0] * (len(edges) + 1)
    for x in xs:
        for i, e in enumerate(edges):
            if x <= e:
                counts[i] += 1
                break
        else:
            counts[-1] += 1
    return _column([float(c) for c in counts])


@fn("STEYX", least=2, most=2)
def STEYX(ys, xs):
    from .functions import _pairs
    sx, sy, _xu, (dy, uy) = _pairs(ys, xs)
    n = len(sx)
    if n < 3:
        return DIV0
    mx, my = math.fsum(sx) / n, math.fsum(sy) / n
    sxx = math.fsum((x - mx) ** 2 for x in sx)
    syy = math.fsum((y - my) ** 2 for y in sy)
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(sx, sy))
    if sxx == 0:
        return DIV0
    return rebuild(math.sqrt(max(0.0, (syy - sxy * sxy / sxx) / (n - 2))), dy, uy)


@fn("COMBINA", least=2, most=2, lift=(0, 1))
def COMBINA(n, k):
    a, b = int(real(n)), int(real(k))
    if a < 0 or b < 0:
        return NUM
    return float(math.comb(a + b - 1, b)) if a + b > 0 else 1.0


@fn("PERMUTATIONA", least=2, most=2, lift=(0, 1))
def PERMUTATIONA(n, k):
    a, b = int(real(n)), int(real(k))
    if a < 0 or b < 0:
        return NUM
    return float(a ** b)


@fn("MULTINOMIAL", least=1)
def MULTINOMIAL(*args):
    ks = [int(x) for x in _floats(args)]
    if any(k < 0 for k in ks):
        return NUM
    out = math.factorial(sum(ks))
    for k in ks:
        out //= math.factorial(k)
    return float(out)


@fn("SERIESSUM", least=4, most=4)
def SERIESSUM(x, n, m, coefficients):
    v, a, b = real(x), real(n), real(m)
    cs = [to_float(c) if is_number(c) else _bad() for c in grid(coefficients).values()]
    return math.fsum(c * v ** (a + i * b) for i, c in enumerate(cs))


def _bad():
    raise SheetError(VALUE)


def _two_series(a, b):
    ga, gb = grid(a), grid(b)
    if (ga.height, ga.width) != (gb.height, gb.width):
        raise SheetError(NA)
    return [(to_float(x), to_float(y)) for x, y in zip(ga.values(), gb.values())
            if is_number(x) and is_number(y)]


@fn("SUMX2MY2", least=2, most=2)
def SUMX2MY2(a, b):
    return math.fsum(x * x - y * y for x, y in _two_series(a, b))


@fn("SUMX2PY2", least=2, most=2)
def SUMX2PY2(a, b):
    return math.fsum(x * x + y * y for x, y in _two_series(a, b))


@fn("SUMXMY2", least=2, most=2)
def SUMXMY2(a, b):
    return math.fsum((x - y) ** 2 for x, y in _two_series(a, b))


# -- regression ---------------------------------------------------------------------------------
def _design(known_y, known_x, const=True, log_y=False):
    import numpy as np
    gy = grid(known_y)
    y = np.array([to_float(v) for v in gy.values()], dtype=float)
    if log_y:
        if (y <= 0).any():
            raise SheetError(NUM)
        y = np.log(y)
    n = len(y)
    if known_x is MISSING:
        X = np.arange(1, n + 1, dtype=float).reshape(n, 1)
    else:
        gx = grid(known_x)
        vals = np.array([[to_float(v) for v in row] for row in gx.rows], dtype=float)
        if gy.width == 1 and vals.shape[0] == n:
            X = vals                                   # x variables in columns
        elif gy.height == 1 and vals.shape[1] == n:
            X = vals.T                                 # in rows
        elif vals.size == n:
            X = vals.reshape(n, 1)
        else:
            raise SheetError(VALUE)
    if const:
        A = np.hstack([X, np.ones((n, 1))])
    else:
        A = X
    return A, y, X.shape[1]


def _linest(known_y, known_x, const, stats, log_y=False):
    import numpy as np
    keep = True if const is MISSING else flag(const)
    want = False if stats is MISSING else flag(stats)
    A, y, k = _design(known_y, known_x, keep, log_y)
    n = len(y)
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    slopes = list(coef[:k][::-1])
    b = float(coef[k]) if keep else 0.0
    row0 = [float(c) for c in slopes] + [b]
    if log_y:
        row0 = [math.exp(v) for v in row0]
    if not want:
        return Array((tuple(row0),))
    fitted = A @ coef
    resid = y - fitted
    ss_resid = float(resid @ resid)
    df = n - k - (1 if keep else 0)
    ss_total = float(((y - y.mean()) @ (y - y.mean())) if keep else (y @ y))
    ss_reg = ss_total - ss_resid
    r2 = ss_reg / ss_total if ss_total else 1.0
    se_y = math.sqrt(ss_resid / df) if df > 0 else NA
    try:
        cov = np.linalg.inv(A.T @ A) * (ss_resid / df if df > 0 else float("nan"))
        se = [math.sqrt(max(0.0, cov[i, i])) for i in range(A.shape[1])]
    except np.linalg.LinAlgError:
        se = [float("nan")] * A.shape[1]
    se_row = [se[i] for i in range(k)][::-1] + ([se[k]] if keep else [NA])
    f = (ss_reg / k) / (ss_resid / df) if df > 0 and ss_resid else NA
    width = k + 1
    pad = [NA] * (width - 2)
    rows = [row0, se_row, [r2, se_y] + pad, [f, float(df)] + pad, [ss_reg, ss_resid] + pad]
    return Array(tuple(tuple(v if isinstance(v, ErrorValue) or not isinstance(v, float) or
                             math.isfinite(v) else NUM for v in row) for row in rows))


@fn("LINEST", least=1, most=4)
def LINEST(known_y, known_x=MISSING, const=MISSING, stats=MISSING):
    return _linest(known_y, known_x, const, stats)


@fn("LOGEST", least=1, most=4)
def LOGEST(known_y, known_x=MISSING, const=MISSING, stats=MISSING):
    return _linest(known_y, known_x, const, stats, log_y=True)


@fn("GROWTH", least=1, most=4)
def GROWTH(known_y, known_x=MISSING, new_x=MISSING, const=MISSING):
    import numpy as np
    keep = True if const is MISSING else flag(const)
    A, y, k = _design(known_y, known_x, keep, log_y=True)
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    target = known_x if new_x is MISSING else new_x
    if target is MISSING:
        target = Array(tuple((float(i + 1),) for i in range(len(y))))
    g = grid(target)
    out = []
    if k == 1:
        for row in g.rows:
            out.append(tuple(math.exp(coef[0] * to_float(v) + (coef[1] if keep else 0.0)) for v in row))
    else:
        for row in g.rows:
            xs = [to_float(v) for v in row]
            s = sum(c * x for c, x in zip(coef[:k], xs)) + (coef[k] if keep else 0.0)
            out.append((math.exp(s),))
    return Array(tuple(out))


# -- database functions --------------------------------------------------------------------------
def _database(database, field, criteria):
    db, cr = grid(database), grid(criteria)
    if db.height < 1 or cr.height < 1:
        raise SheetError(VALUE)
    heads = [to_text(v).strip().lower() if v is not BLANK else "" for v in db.rows[0]]
    col = None
    if field is not MISSING:
        f = one(field)
        if is_number(f) and not isinstance(f, bool):
            col = int(to_float(f)) - 1
            if not 0 <= col < db.width:
                raise SheetError(VALUE)
        else:
            name = to_text(f).strip().lower()
            if name not in heads:
                raise SheetError(VALUE)
            col = heads.index(name)
    crit_heads = [to_text(v).strip().lower() if v is not BLANK else "" for v in cr.rows[0]]
    tests = []
    for row in cr.rows[1:]:
        tests_row = []
        for h, c in zip(crit_heads, row):
            if c is BLANK or c == "":
                continue
            if h not in heads:
                raise SheetError(VALUE)
            if isinstance(c, str) and not re.match(r"^(<=|>=|<>|=|<|>)", c) and "*" not in c \
                    and "?" not in c and not c.strip().replace(".", "", 1).isdigit():
                c = c + "*"                   # text in a criteria range: begins with
            tests_row.append((heads.index(h), criterion(c)))
        tests.append(tests_row)
    out = []
    for row in db.rows[1:]:
        if not tests or any(all(t(row[i]) for i, t in tr) for tr in tests):
            out.append(row if col is None else row[col])
    return out


def _d(fname):
    def run(database, field, criteria):
        if field is MISSING and fname in ("COUNT", "COUNTA"):
            return float(len(_database(database, MISSING, criteria)))   # every matching record
        vals = _database(database, field, criteria)
        return FUNCTIONS[fname].fn(Array(tuple((v,) for v in vals)) if vals else Array(((BLANK,),)))
    return run


for _dname, _inner in (("DSUM", "SUM"), ("DAVERAGE", "AVERAGE"), ("DCOUNT", "COUNT"),
                       ("DCOUNTA", "COUNTA"), ("DMAX", "MAX"), ("DMIN", "MIN"), ("DPRODUCT", "PRODUCT"),
                       ("DSTDEV", "STDEV"), ("DSTDEVP", "STDEVP"), ("DVAR", "VAR"), ("DVARP", "VARP")):
    fn(_dname, least=3, most=3)(_d(_inner))


@fn("DGET", least=3, most=3)
def DGET(database, field, criteria):
    vals = _database(database, field, criteria)
    if not vals:
        return VALUE
    if len(vals) > 1:
        return NUM
    return vals[0]


# -- money -----------------------------------------------------------------------------------
def _pmt(r, n, p, f, t):
    return FUNCTIONS["PMT"].fn(r, n, p, f, t)


def _fv(r, n, m, p, t):
    return FUNCTIONS["FV"].fn(r, n, m, p, t)


def _ipmt(r, per, n, p, f, t):
    m = _pmt(r, n, p, f, t)
    if per == 1:
        ip = 0.0 if t == 1 else -p
    elif t == 1:
        ip = _fv(r, per - 2, m, p, 1) - m
    else:
        ip = _fv(r, per - 1, m, p, 0)
    return ip * r, m


@fn("IPMT", least=4, most=6)
def IPMT(rate, per, nper, pv, fv=MISSING, kind=MISSING):
    r, k, n, p = real(rate), real(per), real(nper), real(pv)
    f, t = _opt_real(fv, 0.0), _opt_int(kind, 0)
    if not 1 <= k <= n:
        return NUM
    return _ipmt(r, k, n, p, f, 1 if t else 0)[0]


@fn("PPMT", least=4, most=6)
def PPMT(rate, per, nper, pv, fv=MISSING, kind=MISSING):
    r, k, n, p = real(rate), real(per), real(nper), real(pv)
    f, t = _opt_real(fv, 0.0), _opt_int(kind, 0)
    if not 1 <= k <= n:
        return NUM
    ip, m = _ipmt(r, k, n, p, f, 1 if t else 0)
    return m - ip


def _cumulative(rate, nper, pv, start, end, kind, principal):
    r, n, p = real(rate), real(nper), real(pv)
    a, b, t = integer(start), integer(end), integer(kind)
    if r <= 0 or n <= 0 or p <= 0 or a < 1 or b < a or b > n or t not in (0, 1):
        return NUM
    total = 0.0
    for k in range(a, b + 1):
        ip, m = _ipmt(r, k, n, p, 0.0, t)
        total += (m - ip) if principal else ip
    return total


@fn("CUMIPMT", least=6, most=6)
def CUMIPMT(rate, nper, pv, start, end, kind):
    return _cumulative(rate, nper, pv, start, end, kind, False)


@fn("CUMPRINC", least=6, most=6)
def CUMPRINC(rate, nper, pv, start, end, kind):
    return _cumulative(rate, nper, pv, start, end, kind, True)


@fn("ISPMT", least=4, most=4)
def ISPMT(rate, per, nper, pv):
    n = real(nper)
    if n == 0:
        return DIV0
    return real(pv) * real(rate) * (real(per) / n - 1)


@fn("SLN", least=3, most=3)
def SLN(cost, salvage, life):
    n = real(life)
    if n == 0:
        return DIV0
    return (real(cost) - real(salvage)) / n


@fn("SYD", least=4, most=4)
def SYD(cost, salvage, life, per):
    c, s, n, k = real(cost), real(salvage), real(life), real(per)
    if n <= 0 or not 0 < k <= n:
        return NUM
    return (c - s) * (n - k + 1) * 2 / (n * (n + 1))


@fn("DB", least=4, most=5)
def DB(cost, salvage, life, period, month=MISSING):
    c, s, n, k = real(cost), real(salvage), int(real(life)), int(real(period))
    mo = _opt_int(month, 12)
    if c < 0 or s < 0 or n <= 0 or k <= 0 or not 1 <= mo <= 12 or k > n + (mo < 12):
        return NUM
    rate = round(1 - (s / c) ** (1 / n), 3) if c else 1.0
    total = 0.0
    dep = 0.0
    for p in range(1, k + 1):
        if p == 1:
            dep = c * rate * mo / 12
        elif p == n + 1:
            dep = (c - total) * rate * (12 - mo) / 12
        else:
            dep = (c - total) * rate
        total += dep
    return dep


def _ddb(cost, salvage, life, period, factor):
    """Excel's DDB for one period (LibreOffice's ScGetDDB, which matches it)."""
    rate = factor / life
    if rate >= 1.0:
        rate = 1.0
        old = cost if period == 1 else 0.0
    else:
        old = cost * (1 - rate) ** (period - 1)
    new = cost * (1 - rate) ** period
    return max(0.0, old - salvage if new < salvage else old - new)


@fn("DDB", least=4, most=5)
def DDB(cost, salvage, life, period, factor=MISSING):
    c, s, n, k = real(cost), real(salvage), real(life), real(period)
    f = _opt_real(factor, 2.0)
    if c < 0 or s < 0 or n <= 0 or k <= 0 or k > n or f <= 0:
        return NUM
    return _ddb(c, s, n, k, f)


def _inter_vdb(cost, salvage, life, life1, period, factor):
    total = 0.0
    end = math.ceil(period)
    sln = 0.0
    left = cost - salvage
    straight = False
    for i in range(1, end + 1):
        if not straight:
            ddb = _ddb(cost, salvage, life, float(i), factor)
            sln = left / (life1 - (i - 1))
            if sln > ddb:
                term, straight = sln, True
            else:
                term = ddb
                left -= ddb
        else:
            term = sln
        if i == end:
            term *= period + 1 - end
        total += term
    return total


@fn("VDB", least=5, most=7)
def VDB(cost, salvage, life, start, end, factor=MISSING, no_switch=MISSING):
    """Variable declining balance between two (fractional) periods, going
    over to straight line when that is more unless told not to
    (LibreOffice's algorithm, which matches Excel's)."""
    c, s, n, a, b = real(cost), real(salvage), real(life), real(start), real(end)
    f = _opt_real(factor, 2.0)
    if c < 0 or s < 0 or n <= 0 or a < 0 or b < a or b > n or f <= 0:
        return NUM
    lo, hi = math.floor(a), math.ceil(b)
    if flag(no_switch):
        total = 0.0
        for i in range(lo + 1, hi + 1):
            term = _ddb(c, s, n, float(i), f)
            if i == lo + 1:
                term *= min(b, lo + 1) - a
            elif i == hi:
                term *= b + 1 - hi
            total += term
        return total
    part = 0.0
    if a != lo:
        left = c - _inter_vdb(c, s, n, n, lo, f)
        part += (a - lo) * _inter_vdb(left, s, n, n - lo, 1.0, f)
    if b != hi:
        left = c - _inter_vdb(c, s, n, n, hi - 1, f)
        part += (hi - b) * _inter_vdb(left, s, n, n - (hi - 1), 1.0, f)
    c -= _inter_vdb(c, s, n, n, lo, f)
    return _inter_vdb(c, s, n, n - lo, hi - lo, f) - part


@fn("EFFECT", least=2, most=2, lift=(0, 1))
def EFFECT(nominal, npery):
    r, p = real(nominal), int(real(npery))
    if r <= 0 or p < 1:
        return NUM
    return (1 + r / p) ** p - 1


@fn("NOMINAL", least=2, most=2, lift=(0, 1))
def NOMINAL(effect, npery):
    r, p = real(effect), int(real(npery))
    if r <= 0 or p < 1:
        return NUM
    return p * ((1 + r) ** (1 / p) - 1)


@fn("FVSCHEDULE", least=2, most=2)
def FVSCHEDULE(principal, schedule):
    total = real(principal)
    for v in grid(schedule).values():
        if v is BLANK:
            continue
        total *= 1 + to_float(v)
    return total


@fn("PDURATION", least=3, most=3)
def PDURATION(rate, pv, fv):
    r, p, f = real(rate), real(pv), real(fv)
    if r <= 0 or p <= 0 or f <= 0:
        return NUM
    return (math.log(f) - math.log(p)) / math.log(1 + r)


@fn("RRI", least=3, most=3)
def RRI(nper, pv, fv):
    n, p, f = real(nper), real(pv), real(fv)
    if n <= 0 or p == 0:
        return NUM
    return (f / p) ** (1 / n) - 1


@fn("MIRR", least=3, most=3)
def MIRR(values, finance_rate, reinvest_rate):
    flows = _floats([values])
    fr, rr = real(finance_rate), real(reinvest_rate)
    n = len(flows)
    pos = math.fsum(v / (1 + rr) ** i for i, v in enumerate(flows) if v > 0)
    neg = math.fsum(v / (1 + fr) ** i for i, v in enumerate(flows) if v < 0)
    if pos == 0 or neg == 0 or n < 2:
        return DIV0
    return (-pos * (1 + rr) ** n / (neg * (1 + rr))) ** (1 / (n - 1)) - 1


def _dated_flows(values, dates):
    v, d = list(grid(values).values()), list(grid(dates).values())
    if len(v) != len(d):
        raise SheetError(NUM)
    flows = [to_float(x) for x in v]
    days = [int(to_float(x)) for x in d]
    if any(x < days[0] for x in days):
        raise SheetError(NUM)
    return flows, days


@fn("XNPV", least=3, most=3)
def XNPV(rate, values, dates):
    r = real(rate)
    flows, days = _dated_flows(values, dates)
    return math.fsum(f / (1 + r) ** ((d - days[0]) / 365) for f, d in zip(flows, days))


@fn("XIRR", least=2, most=3)
def XIRR(values, dates, guess=MISSING):
    flows, days = _dated_flows(values, dates)
    if not any(f > 0 for f in flows) or not any(f < 0 for f in flows):
        return NUM
    r = _opt_real(guess, 0.1)
    t = [(d - days[0]) / 365 for d in days]
    for _ in range(200):
        f = math.fsum(c / (1 + r) ** x for c, x in zip(flows, t))
        df = math.fsum(-x * c / (1 + r) ** (x + 1) for c, x in zip(flows, t))
        if df == 0:
            return NUM
        step = f / df
        r -= step
        if r <= -1:
            r = -0.999999
        if abs(step) < 1e-12:
            return r
    return NUM


@fn("ACCRINT", least=6, most=8)
def ACCRINT(issue, first_interest, settlement, rate, par, frequency, basis=MISSING, calc_method=MISSING):
    r, p, freq = real(rate), real(par), integer(frequency)
    if r <= 0 or p <= 0 or freq not in (1, 2, 4):
        return NUM
    yf = FUNCTIONS["YEARFRAC"].fn(issue, settlement, basis)
    if isinstance(yf, ErrorValue):
        return yf
    return p * r * yf


# -- text, information and arrays ----------------------------------------------------------------
@fn("ASC", least=1, most=1, lift=(0,))
def ASC(value):
    out = []
    for ch in text(value):
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:
            ch = chr(o - 0xFEE0)
        elif o == 0x3000:
            ch = " "
        elif 0xFF61 <= o <= 0xFF9F or unicodedata.east_asian_width(ch) == "F":
            ch = unicodedata.normalize("NFKC", ch)
        out.append(ch)
    return "".join(out)


@fn("ENCODEURL", least=1, most=1, lift=(0,))
def ENCODEURL(value):
    return urllib.parse.quote(text(value), safe="")


@fn("HYPERLINK", least=1, most=2)
def HYPERLINK(link, friendly=MISSING):
    if friendly is MISSING:
        return text(link)
    v = one(friendly)
    return v


def _value_text(v, strict: bool) -> str:
    if isinstance(v, ErrorValue):
        return v.code
    if v is BLANK:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, str):
        return '"' + v.replace('"', '""') + '"' if strict else v
    return to_text(v)


@fn("VALUETOTEXT", least=1, most=2, lift=(0,))
def VALUETOTEXT(value, fmt=MISSING):
    strict = _opt_int(fmt, 0)
    if strict not in (0, 1):
        return VALUE
    v = one(value) if not isinstance(value, ErrorValue) else value
    return _value_text(v, bool(strict))


@fn("ARRAYTOTEXT", least=1, most=2)
def ARRAYTOTEXT(array, fmt=MISSING):
    strict = _opt_int(fmt, 0)
    if strict not in (0, 1):
        return VALUE
    g = grid(array)
    if not strict:
        return ", ".join(_value_text(v, False) for v in g.values())
    return "{" + ";".join(",".join(_value_text(v, True) for v in row) for row in g.rows) + "}"


def _pad(v):
    return NA if v is MISSING else one(v) if not isinstance(v, ErrorValue) else v


@fn("EXPAND", least=2, most=4)
def EXPAND(array, rows, cols=MISSING, pad_with=MISSING):
    g = grid(array)
    r = g.height if one(rows) is BLANK else integer(rows)
    c = g.width if cols is MISSING or one(cols) is BLANK else integer(cols)
    if r < g.height or c < g.width:
        return VALUE
    pad = _pad(pad_with)
    return Array(tuple(tuple(g.get(i, j) if i < g.height and j < g.width else pad for j in range(c))
                       for i in range(r)))


def _wrap(vector, count, pad_with, by_rows):
    g = grid(vector)
    if g.height > 1 and g.width > 1:
        return VALUE
    k = integer(count)
    if k < 1:
        return NUM
    vals = list(g.values())
    pad = _pad(pad_with)
    lines = [vals[i:i + k] for i in range(0, len(vals), k)]
    lines = [line + [pad] * (k - len(line)) for line in lines]
    if by_rows:
        return Array(tuple(tuple(line) for line in lines))
    return Array(tuple(tuple(line[i] for line in lines) for i in range(k)))


@fn("WRAPROWS", least=2, most=3)
def WRAPROWS(vector, count, pad_with=MISSING):
    return _wrap(vector, count, pad_with, True)


@fn("WRAPCOLS", least=2, most=3)
def WRAPCOLS(vector, count, pad_with=MISSING):
    return _wrap(vector, count, pad_with, False)


@fn("AREAS", least=1, most=1, lazy=True)
def AREAS(ctx, args):
    got = ev(args[0], ctx)
    if not isinstance(got, RefValue):
        return VALUE
    return 1.0


@fn("SHEETS", least=0, most=1, lazy=True)
def SHEETS(ctx, args):
    if not args:
        return float(len(ctx.wb.sheets))
    got = ev(args[0], ctx)
    if not isinstance(got, RefValue):
        return VALUE
    return 1.0


@fn("ISOMITTED", least=1, most=1, lazy=True)
def ISOMITTED(ctx, args):
    from . import formula as F
    node = args[0]
    if isinstance(node, F.Name) and ctx.lets:
        return node.name.lower() in ctx.lets.get(_OMITTED, ())
    return False


@fn("CELL", least=1, most=2, lazy=True)
def CELL(ctx, args):
    from .refs import col_letters
    what = to_text(one(ev(args[0], ctx))).strip().lower()
    ref = ev(args[1], ctx) if len(args) > 1 else None
    if ref is not None and not isinstance(ref, RefValue):
        return VALUE
    sheet = ref.sheet if ref is not None else ctx.sheet
    row = ref.top if ref is not None else ctx.row
    col = ref.left if ref is not None else ctx.col
    value = ctx.wb.value(sheet, row, col)
    if what == "address":
        return f"${col_letters(col)}${row + 1}"
    if what == "row":
        return float(row + 1)
    if what == "col":
        return float(col + 1)
    if what == "contents":
        return 0.0 if value is BLANK else value
    if what == "type":
        return "b" if value is BLANK else "l" if isinstance(value, str) else "v"
    if what == "width":
        return float(int(sheet.width(col) / 48 * 8.43))     # in characters: 48 pt is Excel's 8
    if what == "filename":
        return f"[{ctx.wb.title}]{sheet.name}" if getattr(ctx.wb, "title", "") else sheet.name
    if what == "prefix":
        return "'" if isinstance(value, str) else ""
    if what == "protect":
        return 0.0
    if what in ("format", "color", "parentheses"):
        return "G" if what == "format" else 0.0
    return VALUE


@fn("INFO", least=1, most=1)
def INFO(type_text):
    import platform
    what = text(type_text).strip().lower()
    known = {"recalc": "Automatic", "system": "pcdos", "release": "16.0", "origin": "$A:$A$1",
             "osversion": f"{platform.system()} {platform.release()}", "directory": ""}
    if what == "numfile":
        return 1.0
    return known.get(what, NA)


# -- CONVERT, in Excel's own unit codes ---------------------------------------------------------------
# (SI factor, a SMath unit with the same dimensions, offset). Only codes that
# Excel spells differently from SMath, or that mean something else in SMath
# ("C" is Celsius to Excel, coulomb to SMath; "h" is horsepower; "e" is erg).
EXCEL_UNITS = {
    "C": (1.0, "K", 273.15), "cel": (1.0, "K", 273.15), "F": (5 / 9, "K", 255.3722222222222),
    "fah": (5 / 9, "K", 255.3722222222222), "K": (1.0, "K", 0.0), "kel": (1.0, "K", 0.0),
    "Rank": (5 / 9, "K", 0.0), "Reau": (1.25, "K", 273.15),
    "g": (1e-3, "kg", 0.0), "sg": (14.59390294, "kg", 0.0), "lbm": (0.45359237, "kg", 0.0),
    "u": (1.66053886282e-27, "kg", 0.0), "ozm": (0.028349523125, "kg", 0.0),
    "grain": (6.479891e-5, "kg", 0.0), "cwt": (45.359237, "kg", 0.0), "shweight": (45.359237, "kg", 0.0),
    "uk_cwt": (50.80234544, "kg", 0.0), "lcwt": (50.80234544, "kg", 0.0), "hweight": (50.80234544, "kg", 0.0),
    "stone": (6.35029318, "kg", 0.0), "ton": (907.18474, "kg", 0.0), "uk_ton": (1016.0469088, "kg", 0.0),
    "LTON": (1016.0469088, "kg", 0.0), "brton": (1016.0469088, "kg", 0.0),
    "m": (1.0, "m", 0.0), "mi": (1609.344, "m", 0.0), "Nmi": (1852.0, "m", 0.0), "in": (0.0254, "m", 0.0),
    "ft": (0.3048, "m", 0.0), "yd": (0.9144, "m", 0.0), "ang": (1e-10, "m", 0.0), "ell": (1.143, "m", 0.0),
    "ly": (9.46073047258e15, "m", 0.0), "parsec": (3.08567758128e16, "m", 0.0),
    "pc": (3.08567758128e16, "m", 0.0), "Picapt": (0.0254 / 72, "m", 0.0), "Pica": (0.0254 / 72, "m", 0.0),
    "pica": (0.0254 / 6, "m", 0.0), "survey_mi": (1609.347218694, "m", 0.0),
    "yr": (31557600.0, "s", 0.0), "day": (86400.0, "s", 0.0), "d": (86400.0, "s", 0.0),
    "hr": (3600.0, "s", 0.0), "mn": (60.0, "s", 0.0), "min": (60.0, "s", 0.0), "sec": (1.0, "s", 0.0),
    "s": (1.0, "s", 0.0),
    "Pa": (1.0, "Pa", 0.0), "p": (1.0, "Pa", 0.0), "atm": (101325.0, "Pa", 0.0), "at": (101325.0, "Pa", 0.0),
    "mmHg": (133.322, "Pa", 0.0), "psi": (6894.75729316836, "Pa", 0.0), "Torr": (133.322368421053, "Pa", 0.0),
    "N": (1.0, "N", 0.0), "dyn": (1e-5, "N", 0.0), "dy": (1e-5, "N", 0.0), "lbf": (4.4482216152605, "N", 0.0),
    "pond": (9.80665e-3, "N", 0.0),
    "J": (1.0, "J", 0.0), "e": (1e-7, "J", 0.0), "c": (4.184, "J", 0.0), "cal": (4.1868, "J", 0.0),
    "eV": (1.60217653e-19, "J", 0.0), "ev": (1.60217653e-19, "J", 0.0), "HPh": (2684519.53769617, "J", 0.0),
    "hh": (2684519.53769617, "J", 0.0), "Wh": (3600.0, "J", 0.0), "wh": (3600.0, "J", 0.0),
    "flb": (1.3558179483314, "J", 0.0), "BTU": (1055.05585262, "J", 0.0), "btu": (1055.05585262, "J", 0.0),
    "HP": (745.69987158227, "W", 0.0), "h": (745.69987158227, "W", 0.0), "PS": (735.49875, "W", 0.0),
    "W": (1.0, "W", 0.0), "w": (1.0, "W", 0.0),
    "T": (1.0, "T", 0.0), "ga": (1e-4, "T", 0.0),
    "m/s": (1.0, "m/s", 0.0), "m/sec": (1.0, "m/s", 0.0), "m/h": (1 / 3600, "m/s", 0.0),
    "m/hr": (1 / 3600, "m/s", 0.0), "mph": (0.44704, "m/s", 0.0), "kn": (1852 / 3600, "m/s", 0.0),
    "admkn": (0.514773333333333, "m/s", 0.0),
    "tsp": (4.92892159375e-6, "L", 0.0), "tspm": (5e-6, "L", 0.0), "tbs": (1.478676478125e-5, "L", 0.0),
    "oz": (2.95735295625e-5, "L", 0.0), "cup": (2.365882365e-4, "L", 0.0), "pt": (4.73176473e-4, "L", 0.0),
    "us_pt": (4.73176473e-4, "L", 0.0), "uk_pt": (5.6826125e-4, "L", 0.0), "qt": (9.46352946e-4, "L", 0.0),
    "uk_qt": (1.1365225e-3, "L", 0.0), "gal": (3.785411784e-3, "L", 0.0), "uk_gal": (4.54609e-3, "L", 0.0),
    "l": (1e-3, "L", 0.0), "L": (1e-3, "L", 0.0), "lt": (1e-3, "L", 0.0), "barrel": (0.158987294928, "L", 0.0),
    "bushel": (0.03523907016688, "L", 0.0), "GRT": (2.8316846592, "L", 0.0), "regton": (2.8316846592, "L", 0.0),
    "MTON": (1.13267386368, "L", 0.0),
    "uk_acre": (4046.8564224, "m^2", 0.0), "us_acre": (4046.87260987425, "m^2", 0.0), "ar": (100.0, "m^2", 0.0),
    "ha": (1e4, "m^2", 0.0), "Morgen": (2500.0, "m^2", 0.0),
    "bit": (1.0, "bit", 0.0), "byte": (8.0, "bit", 0.0),
}
_PREFIXES = {"Y": 1e24, "Z": 1e21, "E": 1e18, "P": 1e15, "T": 1e12, "G": 1e9, "M": 1e6, "k": 1e3,
             "h": 1e2, "da": 1e1, "e": 1e1, "d": 1e-1, "c": 1e-2, "m": 1e-3, "u": 1e-6, "n": 1e-9,
             "p": 1e-12, "f": 1e-15, "a": 1e-18, "z": 1e-21, "y": 1e-24}
_BINARY = {"ki": 2 ** 10, "Mi": 2 ** 20, "Gi": 2 ** 30, "Ti": 2 ** 40, "Pi": 2 ** 50, "Ei": 2 ** 60,
           "Zi": 2 ** 70, "Yi": 2 ** 80}
_METRIC = {"g", "m", "l", "L", "lt", "s", "sec", "Pa", "p", "N", "J", "e", "c", "cal", "eV", "ev", "Wh",
           "wh", "W", "w", "T", "ga", "ang", "m/s", "m/sec", "m/h", "m/hr", "atm", "at", "mmHg", "bit",
           "byte", "u", "pc", "parsec", "ly", "K", "kel", "dyn", "dy", "pond", "Torr"}


def excel_unit(code: str):
    """(SI factor, SMath unit of the same dimensions, offset) for one of
    Excel's CONVERT codes, prefixed ones and m2/ft3 included; None if
    Excel wouldn't know it."""
    if code in EXCEL_UNITS:
        return EXCEL_UNITS[code]
    m = re.fullmatch(r"(.+?)([23])", code)
    if m:
        base = excel_unit(m.group(1))
        if base is None or base[1] != "m" or base[2]:
            return None
        k = int(m.group(2))
        return base[0] ** k, f"m^{k}", 0.0
    for table, allowed in ((_BINARY, {"bit", "byte"}), (_PREFIXES, _METRIC)):
        for prefix, factor in sorted(table.items(), key=lambda kv: -len(kv[0])):
            if code.startswith(prefix) and code[len(prefix):] in allowed:
                f, unit, offset = EXCEL_UNITS[code[len(prefix):]]
                return f * factor, unit, offset
    return None


def excel_convert(x: float, a: str, b: str):
    from .values import unit_parts
    ua, ub = excel_unit(a), excel_unit(b)
    if ua is None or ub is None:
        return None
    if tuple(unit_parts(ua[1])[1]) != tuple(unit_parts(ub[1])[1]):
        return NA
    return (x * ua[0] + ua[2] - ub[2]) / ub[0]


del _src, _sb, _dst, _db, _name, _f, _dname, _inner


# -- Excel 365's newer text and range functions, and the last few ---------------------------------
def _regex(pattern, case_sensitivity):
    flags = 0 if case_sensitivity is MISSING or integer(case_sensitivity) == 0 else re.IGNORECASE
    try:
        return re.compile(text(pattern), flags)
    except re.error:
        raise SheetError(VALUE)


@fn("REGEXTEST", least=2, most=3, lift=(0,))
def REGEXTEST(value, pattern, case_sensitivity=MISSING):
    return _regex(pattern, case_sensitivity).search(text(value)) is not None


@fn("REGEXEXTRACT", least=2, most=4, lift=(0,))
def REGEXEXTRACT(value, pattern, mode=MISSING, case_sensitivity=MISSING):
    """0: the first match; 1: every match (a column); 2: the first match's groups (a row)."""
    rx, t = _regex(pattern, case_sensitivity), text(value)
    how = _opt_int(mode, 0)
    if how == 0:
        m = rx.search(t)
        return m.group(0) if m else NA
    if how == 1:
        found = [m.group(0) for m in rx.finditer(t)]
        return _column(found) if found else NA
    if how == 2:
        m = rx.search(t)
        if not m:
            return NA
        groups = m.groups() or (m.group(0),)
        return Array((tuple(g if g is not None else "" for g in groups),))
    return VALUE


@fn("REGEXREPLACE", least=3, most=5, lift=(0,))
def REGEXREPLACE(value, pattern, replacement, occurrence=MISSING, case_sensitivity=MISSING):
    rx, t = _regex(pattern, case_sensitivity), text(value)
    rep = re.sub(r"\$(\d+)", r"\\\1", text(replacement))      # Excel writes groups as $1
    n = _opt_int(occurrence, 0)
    if n == 0:
        return rx.sub(rep, t)
    hits = list(rx.finditer(t))
    k = n - 1 if n > 0 else len(hits) + n
    if not 0 <= k < len(hits):
        return t
    m = hits[k]
    return t[:m.start()] + m.expand(rep) + t[m.end():]


@fn("ACOTH", least=1, most=1, lift=(0,))
def ACOTH(x):
    v = real(x)
    if abs(v) <= 1:
        return NUM
    return 0.5 * math.log((v + 1) / (v - 1))


@fn("PERCENTOF", least=2, most=2)
def PERCENTOF(subset, everything):
    total = math.fsum(_floats([everything]))
    if total == 0:
        return DIV0
    return math.fsum(_floats([subset])) / total


@fn("DOLLARDE", least=2, most=2, lift=(0, 1))
def DOLLARDE(fractional, fraction):
    x, f = real(fractional), int(real(fraction))
    if f < 0:
        return NUM
    if f == 0:
        return DIV0
    whole = math.trunc(x)
    digits = math.ceil(math.log10(f)) if f > 1 else 1
    return whole + (x - whole) * 10 ** digits / f


@fn("DOLLARFR", least=2, most=2, lift=(0, 1))
def DOLLARFR(decimal, fraction):
    x, f = real(decimal), int(real(fraction))
    if f < 0:
        return NUM
    if f == 0:
        return DIV0
    whole = math.trunc(x)
    digits = math.ceil(math.log10(f)) if f > 1 else 1
    return whole + (x - whole) * f / 10 ** digits


@fn("TRIMRANGE", least=1, most=3, lazy=True)
def TRIMRANGE(ctx, args):
    """The reference without its empty outer rows and columns (1 leading,
    2 trailing, 3 both — the default)."""
    ref = ev(args[0], ctx)
    if not isinstance(ref, RefValue):
        return VALUE
    rows = integer(ev(args[1], ctx)) if len(args) > 1 else 3
    cols = integer(ev(args[2], ctx)) if len(args) > 2 else 3
    filled = [(r - ref.top, c - ref.left) for r, c, v in ref.filled() if v is not BLANK and v != ""]
    if not filled:
        return CALC                        # nothing left (Excel's #CALC!, empty)
    first_row, last_row = min(r for r, _c in filled), max(r for r, _c in filled)
    first_col, last_col = min(c for _r, c in filled), max(c for _r, c in filled)
    top = ref.top + (first_row if rows in (1, 3) else 0)
    bottom = ref.top + (last_row if rows in (2, 3) else ref.height - 1)
    left = ref.left + (first_col if cols in (1, 3) else 0)
    right = ref.left + (last_col if cols in (2, 3) else ref.width - 1)
    return RefValue(ref.sheet, top, left, bottom, right)


def _full_width(t: str) -> str:
    return "".join(chr(ord(ch) + 0xFEE0) if 0x21 <= ord(ch) <= 0x7E else "　" if ch == " " else ch
                   for ch in t)


@fn("JIS", "DBCS", least=1, most=1, lift=(0,))
def JIS(value):
    return _full_width(text(value))


# The byte-counting text functions are the character ones outside double-byte locales
for _b in ("LEFT", "RIGHT", "MID", "LEN", "FIND", "SEARCH", "REPLACE"):
    FUNCTIONS[_b + "B"] = FUNCTIONS[_b]
del _b
