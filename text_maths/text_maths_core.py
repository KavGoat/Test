"""
Shared engine for the four "Text Maths" clipboard calculators.

The .pyw launchers next to this file each call run("<mode>"):

    Text Maths - Pure Maths.pyw                    run("pure")
    Text Maths - Pure Maths and Units.pyw          run("units")
    Text Maths - Variables.pyw                     run("variables")
    Text Maths - Variables with Substitution.pyw   run("substitution")

An AutoHotkey hotkey copies the selected text and runs a launcher. The
launcher reads the clipboard, works out every line that asks for an answer,
puts the result back on the clipboard and presses Ctrl+V so the new text
replaces the selection. If nothing changed, nothing is pasted.

Everything that is not a calculation is left exactly as it was, including
line endings (\\r\\n, \\n, Word's soft breaks) and any trailing newline.
"""

import math
import os
import re
import sys
import time

# ============================================================
# SETTINGS
# ============================================================

DECIMALS = 3            # 1/3 -> 0.333
PASTE_DELAY_S = 0.03    # pause between setting the clipboard and pressing Ctrl+V
MODIFIER_WAIT_S = 1.5   # longest wait for the hotkey's Ctrl/Alt/Shift/Win to be let go
MAX_LINE_LENGTH = 10_000
ERROR_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "text_maths_error.log")


class Mode:
    __slots__ = ("units", "variables", "substitution")

    def __init__(self, units, variables, substitution):
        self.units = units                  # False: only angles (30°, 1.2rad)
        self.variables = variables          # name = value lines are remembered
        self.substitution = substitution    # show the working with values in


MODES = {
    "pure": Mode(units=False, variables=False, substitution=False),
    "units": Mode(units=True, variables=False, substitution=False),
    "variables": Mode(units=True, variables=True, substitution=False),
    "substitution": Mode(units=True, variables=True, substitution=True),
}


class NotACalc(Exception):
    """The text can't be read as maths: bad syntax or an unknown name."""


class UnknownName(NotACalc):
    pass


class CalcError(Exception):
    """The text is maths, but the answer can't be worked out."""


# ============================================================
# DIMENSIONS  (mass, length, time, angle), stored in sixths so
# square and cube roots of units stay exact integers
# ============================================================

SIXTHS = 6


def _dims(mass=0, length=0, time_=0, angle=0):
    return (mass * SIXTHS, length * SIXTHS, time_ * SIXTHS, angle * SIXTHS)


NONE = (0, 0, 0, 0)
MASS = _dims(mass=1)
LENGTH = _dims(length=1)
TIME = _dims(time_=1)
ANGLE = _dims(angle=1)
FORCE = _dims(1, 1, -2)
PRESSURE = _dims(1, -1, -2)
MOMENT = _dims(1, 2, -2)
LINE_LOAD = _dims(1, 0, -2)
UNIT_WEIGHT = _dims(1, -2, -2)
AREA = _dims(length=2)
VOLUME = _dims(length=3)
INERTIA = _dims(length=4)
VELOCITY = _dims(length=1, time_=-1)
ACCELERATION = _dims(length=1, time_=-2)
DENSITY = _dims(1, -3)

DIM_NAMES = {
    NONE: "a plain number", MASS: "a mass", LENGTH: "a length", TIME: "a time",
    ANGLE: "an angle", FORCE: "a force", PRESSURE: "a pressure",
    MOMENT: "a moment", LINE_LOAD: "a force per length", AREA: "an area",
    VOLUME: "a volume", INERTIA: "a second moment of area",
    VELOCITY: "a velocity", ACCELERATION: "an acceleration",
    DENSITY: "a density", UNIT_WEIGHT: "a unit weight",
}


def _dims_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2], a[3] + b[3])


def _dims_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2], a[3] - b[3])


def dim_name(dims):
    return DIM_NAMES.get(dims) or f"something in {unit_text(_base_hint(dims))}"


# ============================================================
# UNITS
# ============================================================

# symbol: (factor to SI, dimensions, printed as)
UNITS = {
    "N": (1.0, FORCE, "N"), "kN": (1e3, FORCE, "kN"), "MN": (1e6, FORCE, "MN"),
    "lbf": (4.4482216152605, FORCE, "lbf"), "kip": (4448.2216152605, FORCE, "kip"),
    "g": (1e-3, MASS, "g"), "kg": (1.0, MASS, "kg"), "t": (1e3, MASS, "t"),
    "mm": (1e-3, LENGTH, "mm"), "cm": (1e-2, LENGTH, "cm"),
    "m": (1.0, LENGTH, "m"), "km": (1e3, LENGTH, "km"),
    "in": (0.0254, LENGTH, "in"), "ft": (0.3048, LENGTH, "ft"),
    "s": (1.0, TIME, "s"), "min": (60.0, TIME, "min"), "hr": (3600.0, TIME, "hr"),
    "Pa": (1.0, PRESSURE, "Pa"), "kPa": (1e3, PRESSURE, "kPa"),
    "MPa": (1e6, PRESSURE, "MPa"), "GPa": (1e9, PRESSURE, "GPa"),
    "psi": (6894.757293168, PRESSURE, "psi"),
    "ksi": (6894757.293168, PRESSURE, "ksi"),
    "rad": (1.0, ANGLE, "rad"), "deg": (math.pi / 180.0, ANGLE, "°"),
}
ANGLE_UNITS = frozenset(("rad", "deg"))
ALL_UNITS = frozenset(UNITS)

# Other spellings, matched ignoring case. They are corrected in the text:
# 5kn -> 5kN, 3 secs -> 3 s.
UNIT_SPELLINGS = {
    "sec": "s", "secs": "s", "second": "s", "seconds": "s",
    "mins": "min", "minute": "min", "minutes": "min",
    "hrs": "hr", "hour": "hr", "hours": "hr",
    "degs": "deg", "degree": "deg", "degrees": "deg",
    "kgs": "kg", "tonne": "t", "tonnes": "t", "kips": "kip",
    "m": "m",       # 6M -> 6m; other single letters (n, S, G, T) stay exact
}
# Any capitalisation of a unit of two or more letters: KN, Mpa, KG, MM.
# Other single letters must be exact (N, s, g, t), and mn is left out because
# 5mn -> 5MN would be a million times out.
_UNITS_BY_LOWER = {s.lower(): s for s in UNITS if len(s) > 1 and s.lower() != "mn"}

FORCE_SYMBOLS = sorted((s for s, u in UNITS.items() if u[1] == FORCE),
                       key=len, reverse=True)
LENGTH_SYMBOLS = frozenset(s for s, u in UNITS.items() if u[1] == LENGTH)
_LENGTH_BY_LOWER = {s.lower(): s for s in LENGTH_SYMBOLS}

# Order units are printed in: kN before m (kNm), kg before m/s².
_RANK = {FORCE: 0, MASS: 1, PRESSURE: 2, LENGTH: 3, TIME: 4, ANGLE: 5}

SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺"
_FROM_SUPERSCRIPT = str.maketrans(SUPERSCRIPTS, "0123456789-+")
_TO_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")

# A "hint" is the unit an answer is printed in, kept as a tuple of
# (symbol, power in sixths) pairs: kN/m -> (("kN", 6), ("m", -6)).
_hint_cache = {}


def hint_factor_dims(hint):
    cached = _hint_cache.get(hint)
    if cached is None:
        factor, dims = 1.0, NONE
        for symbol, power in hint:
            unit_factor, unit_dims, _ = UNITS[symbol]
            factor *= unit_factor ** (power / SIXTHS)
            dims = _dims_add(dims, tuple(d * power // SIXTHS for d in unit_dims))
        cached = _hint_cache[hint] = (factor, dims)
    return cached


def _power_text(power):
    if power % SIXTHS == 0:
        whole = power // SIXTHS
        return "" if whole == 1 else str(whole).translate(_TO_SUPERSCRIPT)
    return "^" + format_number(power / SIXTHS)


def unit_text(hint):
    """(("kN",6),("m",-6)) -> 'kN/m'.  Force x length prints as kNm."""
    ranked = sorted(hint, key=lambda item: _RANK.get(UNITS[item[0]][1], 9))
    top = [(s, p) for s, p in ranked if p > 0]
    bottom = [(s, -p) for s, p in ranked if p < 0]
    if (len(top) == 2 and top[0][1] == top[1][1] == SIXTHS
            and UNITS[top[0][0]][1] == FORCE and UNITS[top[1][0]][1] == LENGTH):
        text = UNITS[top[0][0]][2] + UNITS[top[1][0]][2]
    else:
        text = "·".join(UNITS[s][2] + _power_text(p) for s, p in top) or "1"
    for symbol, power in bottom:
        text += "/" + UNITS[symbol][2] + _power_text(power)
    return text


def _base_hint(dims):
    return tuple((s, p) for s, p in zip(("kg", "m", "s", "rad"), dims) if p)


def _clean(hint, dims):
    """Is this combined unit worth printing, or should we pick one ourselves?"""
    if not hint or len(hint) > 3:
        return False
    if dims in (FORCE, PRESSURE):       # kg·m/s² -> kN, N/mm² -> MPa
        return len(hint) == 1 and hint[0][1] == SIXTHS
    seen = set()
    for symbol, _ in hint:
        family = UNITS[symbol][1]
        if family in seen:              # mm and m together: not tidy
            return False
        seen.add(family)
    if MASS in seen and TIME in seen:   # kg/m³ × m/s² -> kN/m³
        return False
    return not (PRESSURE in seen and (LENGTH in seen or FORCE in seen))


def _run_symbols(run, allowed):
    """A run of letters as unit symbols: 'mm' -> ['mm'], 'kNm' -> ['kN','m'],
    'kn' -> ['kN'].  The correct spelling is "".join(symbols)."""
    if run == "°":
        symbol = "deg"
    elif run in UNITS:
        symbol = run
    else:
        lower = run.lower()
        symbol = UNIT_SPELLINGS.get(lower) or (_UNITS_BY_LOWER.get(lower) if len(run) > 1 else None)
    if symbol:
        return [symbol] if symbol in allowed else None
    lower = run.lower()
    for force in FORCE_SYMBOLS:         # kNm, Nmm, MNm (any case) and nothing else
        if lower.startswith(force.lower()) and force in allowed:
            length = _LENGTH_BY_LOWER.get(lower[len(force):])
            if length and (run.startswith(force) or force != "MN"):
                return [force, length]
    return None


_INT = re.compile(r"[+-]?\d+")


def _scan_power(text, pos):
    """Power written after a unit: m^2, m², m2.  Returns (power, end)."""
    n = len(text)
    if pos < n and text[pos] == "^":
        match = _INT.match(text, pos + 1)
        if match:
            return int(match.group()), match.end()
    elif pos < n and text[pos] in SUPERSCRIPTS:
        end = pos
        while end < n and text[end] in SUPERSCRIPTS:
            end += 1
        try:
            return int(text[pos:end].translate(_FROM_SUPERSCRIPT)), end
        except ValueError:
            pass
    elif pos < n and text[pos].isascii() and text[pos].isdigit():
        end = pos
        while end < n and text[end].isascii() and text[end].isdigit():
            end += 1
        if not (end < n and (text[end] == "." or _is_name_char(text[end]))):
            return int(text[pos:end]), end
    return 1, pos


def scan_unit(text, pos, allowed, variables=None, fixes=None):
    """
    Read a unit such as kN, mm², kN/m, kNm or m/s^2 starting at pos.

    Returns (hint, end) or None. A unit never swallows a function call
    (s·in is not 'sin(') and stops before a name that is a variable.
    Misspelt units (kn, Mpa) and plain powers (m2, m^2) are added to
    fixes as (start, end, correct).
    """
    n = len(text)
    totals = {}
    committed = None
    sign, start = 1, pos
    while True:
        if start < n and text[start] == "°":
            run, end = "°", start + 1
        else:
            end = start
            while end < n and text[end].isascii() and text[end].isalpha():
                end += 1
            run = text[start:end]
            if not run or (end < n and (text[end] in "(_'"
                                        or (text[end].isalpha() and not text[end].isascii()))):
                break
        symbols = _run_symbols(run, allowed)
        if not symbols or (committed and variables and run in variables):
            break
        if fixes is not None and run != "°" and run != "".join(symbols):
            fixes.append((start, end, "".join(symbols)))
        power_start = end
        power, end = _scan_power(text, end)
        if fixes is not None and end > power_start:
            neat = "" if power == 1 else str(power).translate(_TO_SUPERSCRIPT)
            if text[power_start:end] != neat:           # m2, m^2 -> m²
                fixes.append((power_start, end, neat))
        for symbol in symbols:
            totals[symbol] = totals.get(symbol, 0) + sign * power * SIXTHS
        committed = end
        if (end + 1 < n and text[end] in "/*·⋅"
                and (text[end + 1] == "°" or (text[end + 1].isascii() and text[end + 1].isalpha()))):
            sign = -1 if text[end] == "/" else 1
            start = end + 1
            continue
        break
    if committed is None:
        return None
    return tuple((s, p) for s, p in totals.items() if p), committed


def parse_unit(text, allowed=ALL_UNITS):
    """A whole string as a unit ('mm', '(kN/m)'), or None."""
    found = _parse_unit_fixed(text, allowed)
    return found and found[0]


def _parse_unit_fixed(text, allowed):
    """(hint, text with the spelling corrected) or None."""
    stripped = text.strip()
    inner = stripped
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1].strip()
    fixes = []
    found = scan_unit(inner, 0, allowed, fixes=fixes) if inner else None
    if found and found[1] == len(inner) and found[0]:
        return found[0], stripped.replace(inner, apply_fixes(inner, fixes), 1)
    return None


def apply_fixes(text, fixes, offset=0):
    """Splice corrected unit spellings into text (fix positions minus offset)."""
    for start, end, correct in sorted(fixes, reverse=True):
        text = text[:start - offset] + correct + text[end - offset:]
    return text


# ============================================================
# QUANTITY
# ============================================================

class Q:
    """A number with dimensions and the unit it should be printed in."""
    __slots__ = ("v", "d", "h")

    def __init__(self, value, dims=NONE, hint=None):
        self.v = value
        self.d = dims
        self.h = hint

    def __repr__(self):
        return f"Q({format_quantity(self)})"


def _no_lists(*values):
    for value in values:
        if isinstance(value, list):
            raise CalcError("can't do arithmetic on a list of values")


def add(a, b, verb="add"):
    _no_lists(a, b)
    if a.d != b.d:
        raise CalcError(f"can't {verb} {dim_name(a.d)} and {dim_name(b.d)}")
    return Q(a.v + b.v if verb == "add" else a.v - b.v, a.d, a.h or b.h)


def sub(a, b):
    return add(a, b, "subtract")


def _combine(a, b, sign, dims):
    if dims == NONE:
        return None
    if (a.d != NONE and a.h is None) or (b.d != NONE and b.h is None):
        return None
    totals = dict(a.h or ())
    for symbol, power in b.h or ():
        totals[symbol] = totals.get(symbol, 0) + sign * power
    hint = tuple((s, p) for s, p in totals.items() if p)
    return hint if _clean(hint, dims) else None


def mul(a, b):
    _no_lists(a, b)
    dims = _dims_add(a.d, b.d)
    return Q(a.v * b.v, dims, _combine(a, b, 1, dims))


def div(a, b):
    _no_lists(a, b)
    if b.v == 0:
        raise CalcError("division by zero")
    dims = _dims_sub(a.d, b.d)
    return Q(a.v / b.v, dims, _combine(a, b, -1, dims))


def neg(a):
    _no_lists(a)
    return Q(-a.v, a.d, a.h)


def _whole(x):
    rounded = round(x)
    return rounded if abs(x - rounded) < 1e-9 else None


def pw(a, b):
    _no_lists(a, b)
    if b.d != NONE:
        raise CalcError("a power must be a plain number")
    p = b.v
    result = a.v ** p
    if isinstance(result, complex):
        raise CalcError("negative number to a fractional power")
    if a.d == NONE:
        return Q(result)
    dims = tuple(_whole(x * p) for x in a.d)
    if None in dims:
        raise CalcError(f"can't raise {dim_name(a.d)} to the power {format_number(p)}")
    hint = None
    if a.h:
        powers = [_whole(power * p) for _, power in a.h]
        if None not in powers:
            hint = tuple((s, q) for (s, _), q in zip(a.h, powers))
    return Q(result, dims, hint)


# ============================================================
# FUNCTIONS
# ============================================================

DEG = (("deg", SIXTHS),)
RAD = (("rad", SIXTHS),)


def _plain(x, name):
    if isinstance(x, list) or x.d != NONE:
        raise CalcError(f"{name}() needs a plain number")
    return x.v


def _radians(x, name):
    """Plain numbers are degrees."""
    if isinstance(x, list):
        raise CalcError(f"{name}() needs an angle")
    if x.d == ANGLE:
        return x.v
    if x.d == NONE:
        return math.radians(x.v)
    raise CalcError(f"{name}() needs an angle, not {dim_name(x.d)}")


def _unit_interval(x, name):
    value = _plain(x, name)
    if abs(abs(value) - 1) < 1e-12:
        value = math.copysign(1.0, value)
    if not -1 <= value <= 1:
        raise CalcError(f"{name}() needs a value between -1 and 1")
    return value


def _values(args, name):
    if len(args) == 1 and isinstance(args[0], list):
        args = args[0]
    if not args:
        raise CalcError(f"{name}() needs at least one value")
    _no_lists(*args)
    if any(a.d != args[0].d for a in args):
        raise CalcError(f"{name}() values must all have the same kind of unit")
    return args


def _display_rounding(rounder):
    def apply(x, places=None):
        _no_lists(x)
        hint = x.h or auto_hint(x)
        factor = hint_factor_dims(hint)[0] if hint else 1.0
        scaled = x.v / factor
        if places is None:
            rounded = rounder(scaled)
        else:
            digits = int(_plain(places, "round"))
            rounded = rounder(scaled * 10 ** digits) / 10 ** digits
        return Q(float(rounded) * factor, x.d, x.h)
    return apply


def _lin_int(p1, p2, x3):
    if not (isinstance(p1, list) and isinstance(p2, list) and len(p1) == len(p2) == 2):
        raise CalcError("lin_int() needs two (x, y) points then an x")
    (x1, y1), (x2, y2) = p1, p2
    xs, ys = _values([x1, x2, x3], "lin_int"), _values([y1, y2], "lin_int")
    if xs[0].v == xs[1].v:
        raise CalcError("lin_int(): the two x values can't be equal")
    ratio = (xs[2].v - xs[0].v) / (xs[1].v - xs[0].v)
    return Q(y1.v + ratio * (y2.v - y1.v), y1.d, y1.h or y2.h)


def _sqrt(x):
    _no_lists(x)
    if x.v < 0:
        raise CalcError("square root of a negative number")
    return pw(x, Q(0.5))


def _cbrt(x):
    _no_lists(x)
    root = pw(Q(abs(x.v), x.d, x.h), Q(1 / 3))
    return Q(math.copysign(root.v, x.v), root.d, root.h)


def _log(x, base=None):
    value = _plain(x, "log")
    if base is None:
        return Q(math.log(value))
    return Q(math.log(value, _plain(base, "log")))


def _atan2(y, x):
    y, x = _values([y, x], "atan2")
    return Q(math.atan2(y.v, x.v), ANGLE, DEG)


def _to_radians(x):
    if not isinstance(x, list) and x.d == ANGLE:
        return Q(x.v, ANGLE, RAD)
    return Q(math.radians(_plain(x, "radians")), ANGLE, RAD)


def _to_degrees(x):
    """degrees(angle) shows it in degrees; degrees(plain) reads it as radians."""
    if not isinstance(x, list) and x.d == ANGLE:
        return Q(x.v, ANGLE, DEG)
    return Q(_plain(x, "degrees"), ANGLE, DEG)


def _pick(chooser, name):
    def apply(*args):
        values = _values(list(args), name)
        best = chooser(values, key=lambda q: q.v)
        return Q(best.v, best.d, best.h)
    return apply


def _abs(x):
    _no_lists(x)
    return Q(abs(x.v), x.d, x.h)


FUNCTIONS = {
    "sin": lambda x: Q(math.sin(_radians(x, "sin"))),
    "cos": lambda x: Q(math.cos(_radians(x, "cos"))),
    "tan": lambda x: Q(math.tan(_radians(x, "tan"))),
    "asin": lambda x: Q(math.asin(_unit_interval(x, "asin")), ANGLE, DEG),
    "acos": lambda x: Q(math.acos(_unit_interval(x, "acos")), ANGLE, DEG),
    "atan": lambda x: Q(math.atan(_plain(x, "atan")), ANGLE, DEG),
    "atan2": _atan2,
    "radians": _to_radians, "degrees": _to_degrees,
    "sqrt": _sqrt, "cbrt": _cbrt, "abs": _abs,
    "round": _display_rounding(round),
    "floor": _display_rounding(math.floor),
    "ceil": _display_rounding(math.ceil),
    "min": _pick(min, "min"), "max": _pick(max, "max"),
    "lin_int": _lin_int,
    "log": _log, "ln": lambda x: Q(math.log(_plain(x, "ln"))),
    "log10": lambda x: Q(math.log10(_plain(x, "log10"))),
    "log2": lambda x: Q(math.log2(_plain(x, "log2"))),
    "exp": lambda x: Q(math.exp(_plain(x, "exp"))),
}

CONSTANTS = {"pi": math.pi, "Pi": math.pi, "PI": math.pi, "π": math.pi, "e": math.e}
GRAVITY = 9.81
GRAVITY_HINT = (("m", SIXTHS), ("s", -2 * SIXTHS))


def constant(name, mode):
    if name == "ge":
        return Q(GRAVITY, ACCELERATION, GRAVITY_HINT) if mode.units else Q(GRAVITY)
    value = CONSTANTS.get(name)
    return None if value is None else Q(value)


# ============================================================
# TOKENISER
# ============================================================

_NUMBER = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_OPERATORS = {
    "+": "+", "-": "-", "−": "-", "–": "-", "—": "-",
    "*": "*", "×": "*", "·": "*", "⋅": "*", "∗": "*",
    "/": "/", "÷": "/", "^": "^",
    "(": "(", ")": ")", "[": "(", "]": ")", "{": "(", "}": ")",
    ",": ",", "%": "%", "√": "√",
}
_SPACES = " \t\xa0  "
_SUBSCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉"


def _is_name_char(c):
    return (c.isalpha() or c == "_" or c == "'" or (c.isascii() and c.isdigit())
            or c in _SUBSCRIPT_DIGITS)


def is_name(text):
    return bool(text) and (text[0].isalpha() or text[0] == "_") and all(
        _is_name_char(c) for c in text)


def _unit_start(c):
    return c == "°" or (c.isascii() and c.isalpha())


def tokenize(text, mode, variables, fixes=None):
    """Tokens are (kind, value, start, end); kinds: num name op sup end."""
    allowed = ALL_UNITS if mode.units else ANGLE_UNITS
    tokens, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in _SPACES:
            i += 1
        elif (c.isascii() and c.isdigit()) or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            match = _NUMBER.match(text, i)
            end = match.end()
            found = None
            if end < n and _unit_start(text[end]):
                # 5mm: a unit written straight after a number always wins.
                found = scan_unit(text, end, allowed, variables, fixes)
            else:
                # 5 mm: a unit unless that word is a variable or constant.
                gap = end
                while gap < n and text[gap] in _SPACES:
                    gap += 1
                if gap > end and gap < n and _unit_start(text[gap]):
                    word_end = gap
                    while word_end < n and _is_name_char(text[word_end]):
                        word_end += 1
                    word = text[gap:word_end]
                    if not (variables and word in variables) and word not in CONSTANTS:
                        found = scan_unit(text, gap, allowed, variables, fixes)
            value = float(match.group())
            if found and found[0]:
                factor, dims = hint_factor_dims(found[0])
                tokens.append(("num", Q(value * factor, dims, found[0]), i, found[1]))
                i = found[1]
            else:
                if found:                       # m/m: cancels to a plain number
                    end = found[1]
                tokens.append(("num", Q(value), i, end))
                i = end
        elif c.isalpha() or c == "_":
            end = i + 1
            while end < n and _is_name_char(text[end]):
                end += 1
            tokens.append(("name", text[i:end], i, end))
            i = end
        elif c in SUPERSCRIPTS:
            end = i
            while end < n and text[end] in SUPERSCRIPTS:
                end += 1
            try:
                power = int(text[i:end].translate(_FROM_SUPERSCRIPT))
            except ValueError:
                raise NotACalc("can't read that power") from None
            tokens.append(("sup", power, i, end))
            i = end
        elif c == "*" and text.startswith("**", i):
            tokens.append(("op", "^", i, i + 2))
            i += 2
        elif c in _OPERATORS:
            tokens.append(("op", _OPERATORS[c], i, i + 1))
            i += 1
        else:
            raise NotACalc(f"unexpected character '{c}'")
    tokens.append(("end", None, n, n))
    return tokens


# ============================================================
# PARSER  (evaluates as it reads)
# ============================================================

class Parser:
    def __init__(self, tokens, mode, variables):
        self.tokens = tokens
        self.i = 0
        self.mode = mode
        self.variables = variables
        self.used = []          # (start, end, value) of each variable read

    def _peek_op(self, chars):
        kind, value = self.tokens[self.i][:2]
        return kind == "op" and value in chars

    def parse(self):
        value = self.expr()
        kind, _, start, _ = self.tokens[self.i]
        if kind != "end":
            raise NotACalc(f"didn't expect what's at position {start + 1}")
        return value

    def expr(self):
        value = self.term()
        while self._peek_op("+-"):
            op = self.tokens[self.i][1]
            self.i += 1
            right = self.term()
            value = add(value, right) if op == "+" else sub(value, right)
        return value

    def term(self):
        value = self.unary()
        while True:
            kind, op = self.tokens[self.i][:2]
            if kind == "op" and op in "*/":
                self.i += 1
                right = self.unary()
                value = mul(value, right) if op == "*" else div(value, right)
            elif kind in ("num", "name") or (kind == "op" and op in "(√"):
                value = mul(value, self.power())       # 2x, 2(a+b), 2pi
            else:
                return value

    def unary(self):
        if self._peek_op("+-"):
            op = self.tokens[self.i][1]
            self.i += 1
            value = self.unary()
            return neg(value) if op == "-" else value
        return self.power()

    def power(self):
        value = self.postfix()
        if self._peek_op("^"):
            self.i += 1
            value = pw(value, self.unary())
        return value

    def postfix(self):
        value = self.atom()
        while True:
            kind, extra = self.tokens[self.i][:2]
            if kind == "sup":
                self.i += 1
                value = pw(value, Q(float(extra)))
            elif kind == "op" and extra == "%":
                self.i += 1
                value = mul(value, Q(0.01))
            else:
                return value

    def items(self):
        values = [self.expr()]
        trailing = False
        while self._peek_op(","):
            self.i += 1
            if self._peek_op(")"):
                trailing = True
                break
            values.append(self.expr())
        if not self._peek_op(")"):
            raise NotACalc("a bracket isn't closed")
        self.i += 1
        return values, trailing

    def atom(self):
        kind, value, start, end = self.tokens[self.i]
        self.i += 1
        if kind == "num":
            return value
        if kind == "name":
            function = FUNCTIONS.get(value.lower())
            if function and self._peek_op("("):
                self.i += 1
                args, _ = self.items()
                try:
                    return function(*args)
                except TypeError:
                    raise CalcError(f"{value}() was given the wrong number of values") from None
            if self.variables is not None and value in self.variables:
                found = self.variables[value]
                self.used.append((start, end, found))
                return found
            found = constant(value, self.mode)
            if found is not None:
                if value == "ge":
                    self.used.append((start, end, found))
                return found
            if function:
                raise NotACalc(f"{value} needs brackets: {value}(...)")
            raise UnknownName(f"unknown name '{value}'")
        if kind == "op" and value == "(":
            values, trailing = self.items()
            return values if trailing or len(values) > 1 else values[0]
        if kind == "op" and value == "√":
            return _sqrt(self.postfix())
        if kind == "end":
            raise NotACalc("the sum ends too early")
        raise NotACalc(f"didn't expect what's at position {start + 1}")


def evaluate(text, mode, variables=None, fixes=None):
    """Return (value, [(start, end, value) of variables used]).
    Misspelt units found on the way are added to fixes."""
    try:
        parser = Parser(tokenize(text, mode, variables, fixes), mode, variables)
        value = parser.parse()
    except ZeroDivisionError:
        raise CalcError("division by zero") from None
    except OverflowError:
        raise CalcError("the number is too big") from None
    except RecursionError:
        raise NotACalc("too many brackets") from None
    except ValueError as error:
        raise CalcError(str(error) or "math domain error") from None
    if isinstance(value, list):
        raise CalcError("the answer is a list, not a number")
    return value, parser.used


# ============================================================
# OUTPUT
# ============================================================

def _engineering(value):
    exponent = int(math.floor(math.log10(abs(value)) / 3) * 3)
    mantissa = value / 10 ** exponent
    text = f"{mantissa:.{DECIMALS}f}".rstrip("0").rstrip(".")
    if abs(float(text)) >= 1000:            # 999.9996 rounded up
        exponent += 3
        text = f"{mantissa / 1000:.{DECIMALS}f}".rstrip("0").rstrip(".")
    return f"{text}e{exponent}"


def format_number(value, exact_whole=False):
    """3 decimals, 3 significant figures below 0.1, engineering notation
    (450e6, 1.067e9) outside 0.001 to 1e6."""
    if not math.isfinite(value):
        return str(value)
    size = abs(value)
    if size == 0:
        return "0"
    if exact_whole and size < 1e15 and value == int(value):
        return str(int(value))
    if size >= 1e6 or size < 1e-3:
        return _engineering(value)
    text = f"{value:.3g}" if size < 0.1 else f"{value:.{DECIMALS}f}"
    if "." in text and "e" not in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _named(text):
    found = parse_unit(text)
    assert found, text
    return found


_AUTO = None


def auto_hint(q):
    """The unit to print in when the inputs don't give a tidy one."""
    global _AUTO
    if q.d == NONE:
        return None
    if _AUTO is None:
        _AUTO = {
            LENGTH: "m", MASS: "kg", TIME: "s", ANGLE: "deg",
            LINE_LOAD: "kN/m", INERTIA: "mm^4", VELOCITY: "m/s",
            ACCELERATION: "m/s^2", DENSITY: "kg/m^3", UNIT_WEIGHT: "kN/m^3",
        }
        _AUTO = {dims: _named(text) for dims, text in _AUTO.items()}
    size = abs(q.v)
    if q.d == FORCE:
        return _named("N" if size < 1e3 else "kN")
    if q.d == PRESSURE:
        return _named("kPa" if size < 1e6 else "MPa")
    if q.d == MOMENT:
        return _named("Nm" if size < 1e3 else "kNm")
    if q.d == AREA:
        return _named("mm^2" if size < 0.1 else "m^2")
    if q.d == VOLUME:
        return _named("mm^3" if size < 0.1 else "m^3")
    return _AUTO.get(q.d) or _base_hint(q.d)


def format_quantity(q, hint=None):
    if q.d == NONE:
        return format_number(q.v, exact_whole=True)
    hint = hint or q.h or auto_hint(q)
    return format_number(q.v / hint_factor_dims(hint)[0]) + unit_text(hint)


# ============================================================
# SHOWING THE WORKING  (Variables with Substitution)
# ============================================================

_VALUE_END = set(")].%°" + SUPERSCRIPTS)
_VALUE_START = set("([.√")


def _ends_value(c):
    return c in _VALUE_END or c.isalnum()


def _starts_value(c):
    return c in _VALUE_START or (c.isalnum() and c not in SUPERSCRIPTS)


def substitute(text, used):
    """'w*L^2/8' -> '10kN/m*(6m)^2/8' using the variables the parser read."""
    out = text
    for start, end, value in sorted(used, key=lambda item: item[0], reverse=True):
        shown = format_quantity(value)
        before = text[:start].rstrip(_SPACES)
        after = text[end:].lstrip(_SPACES)
        prev = before[-1:] if before else ""
        nxt = after[:1]
        simple = value.d == NONE and value.v >= 0 and "e" not in shown
        if ((nxt and (nxt in "^%" or nxt in SUPERSCRIPTS) and not simple)
                or (prev in ("^", "√") and not simple)
                or (shown.startswith("-") and prev not in ("", "(", ","))
                or (prev == "/" and value.d != NONE and ("/" in shown or "·" in shown))):
            shown = f"({shown})"
        if prev and _ends_value(prev):
            shown = "*" + shown
            start = len(before)
        if nxt and _starts_value(nxt):
            shown += "*"
            end = len(text) - len(after)
        out = out[:start] + shown + out[end:]
    return out


# ============================================================
# LINES
# ============================================================

_ERROR_NOTE = " [Error: "
_OLD_ANSWER = re.compile(
    r"\s*[+\-−]?\s*(?:(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|inf|nan)(.*)$")
_LINE_ENDS = "\r\n\x0b\x0c\x1c\x1d\x1e\x85  "
_NOT_ASSIGNMENT = ("==", "<=", ">=", "!=", "=>", "=<")


def _strip_error(line):
    cut = line.rfind(_ERROR_NOTE)
    if cut != -1 and line.rstrip().endswith("]"):
        return line[:cut].rstrip()
    return line


def _error(text, message):
    return f"{text.rstrip()}{_ERROR_NOTE}{message}]"


def _read_tail(tail, allowed):
    """
    What's after the last '=':
      ''          -> fresh request           (hint None, stale False)
      'mm' '(mm)' -> answer in mm            (hint mm,   stale False)
      '45kNm'     -> an old answer to redo   (hint kNm,  stale True)
    Anything else is ordinary prose: returns None.
    """
    text = tail.strip()
    if not text:
        return None, False, ""
    found = _parse_unit_fixed(text, allowed)
    if found:
        return found[0], False, found[1]        # 'kn' comes back as 'kN'
    match = _OLD_ANSWER.match(text)
    if match:
        rest = match.group(1).strip()
        if not rest:
            return None, True, ""
        hint = parse_unit(rest, allowed)
        if hint:
            return hint, True, ""
    return False


def process_line(line, mode, variables):
    if "=" not in line or len(line) > MAX_LINE_LENGTH:
        return line
    if line.lstrip().startswith(("#", "//")) or any(op in line for op in _NOT_ASSIGNMENT):
        return line

    work = _strip_error(line)
    parts = work.split("=")
    equals = [i for i, c in enumerate(work) if c == "="]
    first = parts[0].strip()
    allowed = ALL_UNITS if mode.units else ANGLE_UNITS
    name = None

    if is_name(first) and (len(parts) >= 3 or (mode.variables and len(parts) == 2)):
        name = first
        if len(parts) == 2 and parts[1].strip():
            # x = 5kN  : remember it, print nothing
            expression = parts[1].split("#")[0]
            fixes = []
            try:
                value, _ = evaluate(expression, mode, variables, fixes)
            except NotACalc:
                return line
            except CalcError as error:
                return _error(apply_fixes(work, fixes, -(equals[0] + 1)), error)
            variables[name] = value
            return apply_fixes(work, fixes, -(equals[0] + 1))
        if len(parts) == 2:                     # x =   : show x
            expression, cut, tail, start = first, equals[0], "", 0
        else:                                   # x = expr = [working =] answer
            expression, cut, tail, start = parts[1], equals[1], parts[-1], equals[0] + 1
    else:
        expression, cut, tail, start = parts[0], equals[0], parts[-1], 0

    if not expression.strip():
        return line
    read = _read_tail(tail, allowed)
    if read is False:
        return line
    wanted, stale, request = read
    known = variables if mode.variables else None
    fixes = []
    try:
        value, used = evaluate(expression, mode, known, fixes)
    except NotACalc as error:
        if stale:
            return line
        return _error(apply_fixes(work[:cut + 1], fixes, -start), error)
    except CalcError as error:
        head = apply_fixes(work[:cut + 1], fixes, -start)
        return _error(head + (" " + request if request else ""), error)
    head = apply_fixes(work[:cut + 1], fixes, -start)   # 5kn -> 5kN in the text
    if fixes and mode.substitution:
        expression = apply_fixes(expression, fixes)
        value, used = evaluate(expression, mode, known)

    if wanted and value.d != hint_factor_dims(wanted)[1]:
        if stale:
            wanted = None                       # inputs changed kind; pick afresh
        else:
            return _error(f"{head} {request}",
                          f"the answer is {dim_name(value.d)}, not {unit_text(wanted)}")
    if wanted:
        value = Q(value.v, value.d, wanted)
    if name and mode.variables:
        variables[name] = value

    pieces = []
    if mode.substitution and used:
        working = substitute(expression, used).strip()
        if working != expression.strip():
            pieces.append(working)
    answer = format_quantity(value)
    if not pieces or pieces[-1] != answer:
        pieces.append(answer)
    return f"{head} {' = '.join(pieces)}"


def process_text(text, mode):
    if isinstance(mode, str):
        mode = MODES[mode]
    if "=" not in text:
        return text
    variables = {} if mode.variables else None
    out = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip(_LINE_ENDS)
        try:
            new = process_line(body, mode, variables)
        except Exception as error:                      # never lose the user's text
            new = _error(body, f"internal error: {error}") if body.rstrip().endswith("=") else body
        out.append(new + line[len(body):])
    return "".join(out)


# ============================================================
# CLIPBOARD AND PASTE
# ============================================================

class _Windows:
    """Clipboard and Ctrl+V through the Win32 API: no pyperclip/pyautogui,
    so the script starts in a few milliseconds instead of ~0.5 s."""

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    HWND_MESSAGE = -3
    KEYEVENTF_KEYUP = 0x0002
    VK_CONTROL, VK_V = 0x11, 0x56
    MODIFIERS = (0x10, 0x11, 0x12, 0x5B, 0x5C)      # Shift Ctrl Alt LWin RWin

    def __init__(self):
        import ctypes
        from ctypes import wintypes as w
        self.ctypes = ctypes
        u = self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        k = self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        u.OpenClipboard.argtypes = [w.HWND]
        u.OpenClipboard.restype = w.BOOL
        u.CloseClipboard.restype = w.BOOL
        u.EmptyClipboard.restype = w.BOOL
        u.GetClipboardData.argtypes = [w.UINT]
        u.GetClipboardData.restype = w.HANDLE
        u.SetClipboardData.argtypes = [w.UINT, w.HANDLE]
        u.SetClipboardData.restype = w.HANDLE
        u.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE,
                                      w.LPVOID]
        u.CreateWindowExW.restype = w.HWND
        u.DestroyWindow.argtypes = [w.HWND]
        u.GetAsyncKeyState.argtypes = [ctypes.c_int]
        u.GetAsyncKeyState.restype = ctypes.c_short
        u.MapVirtualKeyW.argtypes = [w.UINT, w.UINT]
        u.MapVirtualKeyW.restype = w.UINT
        k.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
        k.GlobalAlloc.restype = w.HGLOBAL
        k.GlobalLock.argtypes = [w.HGLOBAL]
        k.GlobalLock.restype = w.LPVOID
        k.GlobalUnlock.argtypes = [w.HGLOBAL]
        k.GlobalFree.argtypes = [w.HGLOBAL]

        word, dword, long_ = ctypes.c_uint16, ctypes.c_uint32, ctypes.c_int32

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", word), ("wScan", word), ("dwFlags", dword),
                        ("time", dword), ("dwExtraInfo", ctypes.c_size_t)]

        class MOUSEINPUT(ctypes.Structure):          # sizes the union correctly
            _fields_ = [("dx", long_), ("dy", long_), ("mouseData", dword),
                        ("dwFlags", dword), ("time", dword),
                        ("dwExtraInfo", ctypes.c_size_t)]

        class _UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", dword), ("u", _UNION)]

        self.INPUT, self.KEYBDINPUT = INPUT, KEYBDINPUT
        u.SendInput.argtypes = [w.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        u.SendInput.restype = w.UINT

    def _open(self, owner=None):
        # Another program (Office, clipboard history) may hold it briefly.
        for _ in range(100):
            if self.user32.OpenClipboard(owner):
                return
            time.sleep(0.01)
        raise OSError("the clipboard is busy")

    def get(self):
        self._open()
        try:
            handle = self.user32.GetClipboardData(self.CF_UNICODETEXT)
            if not handle:
                return ""
            pointer = self.kernel32.GlobalLock(handle)
            if not pointer:
                return ""
            try:
                return self.ctypes.wstring_at(pointer)
            finally:
                self.kernel32.GlobalUnlock(handle)
        finally:
            self.user32.CloseClipboard()

    def set(self, text):
        data = text.encode("utf-16-le") + b"\0\0"
        memory = self.kernel32.GlobalAlloc(self.GMEM_MOVEABLE, len(data))
        if not memory:
            raise MemoryError("GlobalAlloc failed")
        pointer = self.kernel32.GlobalLock(memory)
        self.ctypes.memmove(pointer, data, len(data))
        self.kernel32.GlobalUnlock(memory)
        # SetClipboardData needs an owner window, or it can fail after EmptyClipboard.
        owner = self.user32.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0,
                                            self.HWND_MESSAGE, None, None, None)
        try:
            self._open(owner)
            try:
                self.user32.EmptyClipboard()
                if not self.user32.SetClipboardData(self.CF_UNICODETEXT, memory):
                    self.kernel32.GlobalFree(memory)
                    raise OSError("SetClipboardData failed")
            finally:
                self.user32.CloseClipboard()
        finally:
            if owner:
                self.user32.DestroyWindow(owner)

    def _held(self):
        return [vk for vk in self.MODIFIERS if self.user32.GetAsyncKeyState(vk) & 0x8000]

    def _send(self, keys):
        inputs = (self.INPUT * len(keys))()
        for slot, (vk, up) in zip(inputs, keys):
            slot.type = 1                                   # INPUT_KEYBOARD
            slot.ki = self.KEYBDINPUT(vk, self.user32.MapVirtualKeyW(vk, 0),
                                      self.KEYEVENTF_KEYUP if up else 0, 0, 0)
        self.user32.SendInput(len(keys), inputs, self.ctypes.sizeof(self.INPUT))

    def paste(self):
        # If the hotkey's Alt/Shift/Win is still down, Ctrl+V would arrive as
        # Ctrl+Alt+V etc. and paste nothing. Wait for the keys to be let go.
        deadline = time.perf_counter() + MODIFIER_WAIT_S
        held = self._held()
        while held and time.perf_counter() < deadline:
            time.sleep(0.005)
            held = self._held()
        keys = [(vk, True) for vk in held]                  # still down: lift them
        keys += [(self.VK_CONTROL, False), (self.VK_V, False),
                 (self.VK_V, True), (self.VK_CONTROL, True)]
        if PASTE_DELAY_S:
            time.sleep(PASTE_DELAY_S)
        self._send(keys)


class _Fallback:
    """macOS / Linux: pyperclip and pyautogui, imported only here."""

    def __init__(self):
        import pyperclip
        self.pyperclip = pyperclip

    def get(self):
        return self.pyperclip.paste()

    def set(self, text):
        self.pyperclip.copy(text)

    def paste(self):
        import pyautogui
        if PASTE_DELAY_S:
            time.sleep(PASTE_DELAY_S)
        pyautogui.hotkey("command" if sys.platform == "darwin" else "ctrl", "v")


def run(mode_name):
    """Clipboard in, calculate, clipboard out, Ctrl+V."""
    try:
        system = _Windows() if sys.platform == "win32" else _Fallback()
        text = system.get()
        if not text:
            return
        result = process_text(text, MODES[mode_name])
        if result == text:
            return                      # nothing to do: leave the selection alone
        system.set(result)
        system.paste()
    except Exception:
        import traceback
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as log:
                log.write(f"\n--- {time.ctime()} ({mode_name}) ---\n")
                traceback.print_exc(file=log)
        except OSError:
            pass
