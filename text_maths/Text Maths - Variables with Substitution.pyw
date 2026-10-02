import ast
import math
import re
import time
import unicodedata
from dataclasses import dataclass
from fractions import Fraction

try:
    import pyautogui
    import pyperclip
except Exception:
    pyautogui = None
    pyperclip = None


# ============================================================
# SETTINGS
# ============================================================

AUTO_PASTE = True
PASTE_KEYS = ("ctrl", "v")     # macOS: ("command", "v")
PASTE_DELAY_S = 0.08

MAX_EXPR_LEN = 50_000
MAX_AST_NODES = 20_000
MAX_AST_DEPTH = 400

PRESSURE_THRESHOLD_PA = 1e5  # 0.1 MPa
# Printing precision
PRINT_SIGFIGS = 3
PRINT_EXPR_SIGFIGS = 12
LAST_EVAL_LINE = ""


def _format_number_for_print(value: float) -> str:
    """Format numbers with 3 decimal places for ordinary values, and
    scientific notation with a 3-decimal mantissa for extreme magnitudes."""
    v = float(value)
    if math.isfinite(v) is False:
        return str(v)
    if v == 0:
        return "0"
    av = abs(v)
    if av >= 1e6:
        s = f"{v:.3e}"
        mantissa, exponent = s.split("e")
        if mantissa.endswith(".000"):
            mantissa = mantissa[:-4]
        return f"{mantissa}e{exponent}"
    if v.is_integer():
        return str(int(v))
    if av < 0.1:
        s = f"{v:.3g}"
    else:
        s = f"{v:.3f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


# ============================================================
# UNICODE NORMALISATION
# ============================================================

_CONFUSABLE_TRANSLATION = str.maketrans({
    "ϕ": "ϕ",
    "Φ": "Φ",
    "ϑ": "θ",
    "Θ": "θ",
    "ϵ": "ε",
    "ϱ": "ρ",
    "Ρ": "ρ",
    "ς": "σ",
    "Σ": "σ",
    "Ω": "Ω",
    "µ": "μ",
    "π": "pi",
    "Π": "pi",
    # various asterisk/multiplication confusables: map to '*' or remove
    "⁎": "⁎",
    "∗": "*",
    "＊": "*",
    "⋅": "*",
    "⋆": "*",
})


def normalize_text(text: str) -> str:
    if not text:
        return text
    text = text.replace("ϕ", "__KEEP_PHI_LOWER__").replace("Φ", "__KEEP_PHI_UPPER__").replace("⁎", "__KEEP_ASTERISK__")
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_CONFUSABLE_TRANSLATION)
    return text.replace("__KEEP_PHI_LOWER__", "ϕ").replace("__KEEP_PHI_UPPER__", "Φ").replace("__KEEP_ASTERISK__", "⁎")


def normalize_identifier(name: str) -> str:
    return normalize_text(name).casefold()


# ============================================================
# UNITS
# ============================================================

@dataclass(frozen=True)
class UnitDef:
    base: str
    factor: float

UNIT_TABLE = {
    "N": UnitDef("N", 1.0),
    "kN": UnitDef("N", 1e3),
    "MN": UnitDef("N", 1e6),

    "kg": UnitDef("kg", 1.0),
    "t": UnitDef("kg", 1e3),
    "m": UnitDef("m", 1.0),
    "mm": UnitDef("m", 1e-3),
    "cm": UnitDef("m", 1e-2),
    "in": UnitDef("m", 0.0254),
    "ft": UnitDef("m", 0.3048),
    "s": UnitDef("s", 1.0),

    "Pa": UnitDef("Pa", 1.0),
    "kPa": UnitDef("Pa", 1e3),
    "MPa": UnitDef("Pa", 1e6),
    "GPa": UnitDef("Pa", 1e9),
    "psi": UnitDef("Pa", 6894.757),
    "kPa": UnitDef("Pa", 1e3),
    "MPa": UnitDef("Pa", 1e6),
    "GPa": UnitDef("Pa", 1e9),

    "rad": UnitDef("rad", 1.0),
    "deg": UnitDef("rad", math.pi / 180.0),
    "°": UnitDef("rad", math.pi / 180.0),
}

UNIT_ALIASES = {
    "n": "N",
    "kn": "kN",
    "mn": "MN",
    "kg": "kg",
    "g": "g",
    "t": "t",
    "m": "m",
    "mm": "mm",
    "cm": "cm",
    "in": "in",
    "ft": "ft",
    "s": "s",
    "pa": "Pa",
    "kpa": "kPa",
    "mpa": "MPa",
    "gpa": "GPa",
    "psi": "psi",
    "rad": "rad",
    "deg": "deg",
}

_SUPERSCRIPTS = {
    "⁰": "^0",
    "¹": "^1",
    "²": "^2",
    "³": "^3",
    "⁴": "^4",
    "⁵": "^5",
    "⁶": "^6",
    "⁷": "^7",
    "⁸": "^8",
    "⁹": "^9",
    "⁻": "-",
}

_MUL_SIGNS = {
    "·": "*",
    "×": "*",
    "∗": "*",
    "＊": "*",
    "⋅": "*",
    "⋆": "*",
    "⁎": "*",
}

PREFERRED_UNIT = {
    "N": "kN",
    "m": "m",
    "rad": "°",
}

_DIM_ORDER = {
    "N": 0,
    "kg": 1,
    "Pa": 2,
    "m": 3,
    "s": 4,
    "rad": 5,
}

_PRESSURE_DIMS = {
    "N": Fraction(1),
    "m": Fraction(-2),
}

# Derived force dimension for kg*m/s^2
_FORCE_DIMS = {
    "kg": Fraction(1),
    "m": Fraction(1),
    "s": Fraction(-2),
}


def _dims_add(a: dict[str, Fraction], b: dict[str, Fraction], sign: int = +1) -> dict[str, Fraction]:
    result = dict(a)
    for key, power in b.items():
        result[key] = result.get(key, Fraction(0)) + sign * power
        if result[key] == 0:
            del result[key]
    return result


def _normalise_unit_expr(expr: str) -> str:
    expr = (expr or "").strip().replace(" ", "")
    for source, target in _MUL_SIGNS.items():
        expr = expr.replace(source, target)
    for source, target in _SUPERSCRIPTS.items():
        expr = expr.replace(source, target)
    return expr


def _parse_concatenated_units(token: str) -> tuple[float, dict[str, Fraction]]:
    keys = sorted(UNIT_TABLE.keys(), key=len, reverse=True)
    position = 0
    factor = 1.0
    dims: dict[str, Fraction] = {}

    while position < len(token):
        if token[position].isdigit():
            raise ValueError(f"Unknown unit segment in '{token}' at '{token[position:]}'")

        end = position
        while end < len(token) and (token[end].isalpha() or token[end] == "°"):
            end += 1

        chunk = token[position:end]
        unit_name = UNIT_ALIASES.get(chunk.lower()) if chunk else None

        if unit_name is None:
            for cand in keys:
                if token.startswith(cand, position):
                    unit_name = cand
                    break

        if unit_name is None:
            raise ValueError(f"Unknown unit segment in '{token}' at '{token[position:]}'")

        ud = UNIT_TABLE[unit_name]
        factor *= ud.factor
        if ud.base == "Pa":
            dims = _dims_add(dims, _PRESSURE_DIMS, +1)
        else:
            dims = _dims_add(dims, {ud.base: Fraction(1)}, +1)

        position += len(unit_name)

    return factor, dims


def parse_unit_expr(unit_expr: str) -> tuple[float, dict[str, Fraction]]:
    normalized = _normalise_unit_expr(unit_expr)
    if not normalized:
        return 1.0, {}

    tokens: list[str] = []
    operators: list[str] = []
    buffer: list[str] = []

    for ch in normalized:
        if ch in "*/":
            if not buffer:
                raise ValueError(f"Bad unit expression: '{unit_expr}'")
            tokens.append("".join(buffer))
            buffer = []
            operators.append(ch)
        else:
            buffer.append(ch)

    if not buffer:
        raise ValueError(f"Bad unit expression: '{unit_expr}'")

    tokens.append("".join(buffer))
    if len(operators) != len(tokens) - 1:
        raise ValueError(f"Bad unit expression: '{unit_expr}'")

    def parse_part(part: str) -> tuple[float, dict[str, Fraction]]:
        if "^" in part:
            base, exponent = part.rsplit("^", 1)
            if exponent == "" or exponent in {"+", "-"}:
                raise ValueError(f"Bad exponent in unit: '{part}'")
            factor, dims = _parse_concatenated_units(base)
            return _apply_power(factor, dims, int(exponent))

        match = re.fullmatch(r"^(.+?)(-?\d+)$", part)
        if match:
            factor, dims = _parse_concatenated_units(match.group(1))
            return _apply_power(factor, dims, int(match.group(2)))

        return _parse_concatenated_units(part)

    total_factor, total_dims = parse_part(tokens[0])
    for op, token in zip(operators, tokens[1:]):
        factor, dims = parse_part(token)
        if op == "*":
            total_factor *= factor
            total_dims = _dims_add(total_dims, dims, +1)
        else:
            total_factor /= factor
            total_dims = _dims_add(total_dims, dims, -1)

    return total_factor, total_dims


def _apply_power(factor: float, dims: dict[str, Fraction], power: int) -> tuple[float, dict[str, Fraction]]:
    if power == 0:
        return 1.0, {}
    return factor ** power, {unit: exp * Fraction(power) for unit, exp in dims.items()}


def _exp_to_str(exponent: Fraction) -> str:
    if exponent == 1:
        return ""
    # Prefer Unicode superscripts for small integer exponents
    if exponent.denominator == 1:
        n = exponent.numerator
        s = str(n)
        sup_map = {
            "0": "⁰",
            "1": "¹",
            "2": "²",
            "3": "³",
            "4": "⁴",
            "5": "⁵",
            "6": "⁶",
            "7": "⁷",
            "8": "⁸",
            "9": "⁹",
            "-": "⁻",
        }
        try:
            return "".join(sup_map[ch] for ch in s)
        except KeyError:
            return f"^{n}"
    return f"^{exponent.numerator}/{exponent.denominator}"


def _choose_pressure_unit(value_pa: float) -> tuple[str, float]:
    if abs(value_pa) < 1e6:
        return "kPa", 1e3
    return "MPa", 1e6


def _dims_to_preferred_unit_expr_and_divisor(dims: dict[str, Fraction], value: float | None = None) -> tuple[str, float]:
    if not dims:
        return "", 1.0

    if dims == _PRESSURE_DIMS:
        if value is None:
            return "MPa", 1e6
        return _choose_pressure_unit(value)

    if dims == {"m": Fraction(2)} and value is not None:
        if abs(value) < 0.1:
            return "mm²", 1e-6

    if dims == {"m": Fraction(4)}:
        return "mm⁴", 1e-12

    numerator: list[str] = []
    denominator: list[str] = []
    divisor = 1.0

    for base, exponent in sorted(dims.items(), key=lambda item: _DIM_ORDER.get(item[0], 99)):
        pref = PREFERRED_UNIT.get(base, base)
        if pref in UNIT_TABLE and UNIT_TABLE[pref].base == base:
            factor = UNIT_TABLE[pref].factor
        else:
            factor = UNIT_TABLE[base].factor
        divisor *= float(factor) ** float(exponent)
        if exponent > 0:
            numerator.append(pref + _exp_to_str(exponent))
        else:
            denominator.append(pref + _exp_to_str(-exponent))

    # If this is a pure force dimension (kg*m/s^2) present, prefer N/kN output
    if dims == _FORCE_DIMS:
        if value is None:
            return "kN", 1e3
        if abs(value) > 10:
            return "kN", 1e3
        return "N", 1.0
    if denominator:
        num_str = "*".join(numerator) if numerator else "1"
        return f"{num_str}/{'*'.join(denominator)}", divisor
    if len(numerator) > 1 and set(numerator) == {"kN", "m"}:
        return "kNm", divisor
    num_str = "*".join(numerator) if len(numerator) > 1 else (numerator[0] if numerator else "1")
    return num_str, divisor


def _pick_preferred_hint(h1: str | None, h2: str | None, dims: dict[str, Fraction]) -> str | None:
    candidates: list[tuple[float, str]] = []
    for hint in (h1, h2):
        if not hint:
            continue
        try:
            factor, hint_dims = parse_unit_expr(hint)
        except Exception:
            continue
        if hint_dims == dims:
            candidates.append((factor, hint))
    if candidates:
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]
    return h1 or h2


class Quantity:
    __slots__ = ("value", "dims", "hint")

    def __init__(self, value, dims=None, hint=None):
        self.value = float(value)
        self.dims = dims or {}
        self.hint = hint

    @staticmethod
    def from_unit(value, unit_expr: str) -> "Quantity":
        factor, dims = parse_unit_expr(unit_expr)
        hint = _canonicalize_unit_token(unit_expr) if dims else None
        return Quantity(float(value) * factor, dims=dims, hint=hint)

    def is_dimensionless(self) -> bool:
        return not self.dims

    def _check_compatible(self, other: "Quantity"):
        if self.dims != other.dims:
            raise ValueError(f"Unit discrepancy: cannot operate on {self} and {other}")

    def __neg__(self) -> "Quantity":
        return Quantity(-self.value, dict(self.dims), self.hint)

    def __pos__(self) -> "Quantity":
        return Quantity(+self.value, dict(self.dims), self.hint)

    def __add__(self, other):
        if isinstance(other, Quantity):
            self._check_compatible(other)
            return Quantity(self.value + other.value, dict(self.dims), _pick_preferred_hint(self.hint, other.hint, self.dims))
        if self.is_dimensionless():
            return Quantity(self.value + float(other), {}, None)
        raise ValueError(f"Unit discrepancy: cannot add {self} and {other}")

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        if isinstance(other, Quantity):
            self._check_compatible(other)
            return Quantity(self.value - other.value, dict(self.dims), _pick_preferred_hint(self.hint, other.hint, self.dims))
        if self.is_dimensionless():
            return Quantity(self.value - float(other), {}, None)
        raise ValueError(f"Unit discrepancy: cannot subtract {other} from {self}")

    def __rsub__(self, other):
        if self.is_dimensionless():
            return Quantity(float(other) - self.value, {}, None)
        raise ValueError(f"Unit discrepancy: cannot subtract {self} from {other}")

    def __mul__(self, other):
        if isinstance(other, Quantity):
            return Quantity(self.value * other.value, _dims_add(self.dims, other.dims, +1), None)
        return Quantity(self.value * float(other), dict(self.dims), self.hint)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if isinstance(other, Quantity):
            return Quantity(self.value / other.value, _dims_add(self.dims, other.dims, -1), None)
        return Quantity(self.value / float(other), dict(self.dims), self.hint)

    def __rtruediv__(self, other):
        return Quantity(float(other) / self.value, _dims_add({}, self.dims, -1), None)

    def __pow__(self, exponent):
        p = float(exponent)
        if abs(p - round(p)) < 1e-12:
            fraction_exp = Fraction(int(round(p)), 1)
        elif abs(p - 0.5) < 1e-12:
            fraction_exp = Fraction(1, 2)
        else:
            raise ValueError("Unit discrepancy: only integer powers and 0.5 are allowed for unit quantities")
        return Quantity(self.value ** p, {k: v * fraction_exp for k, v in self.dims.items()}, None)

    def _compare_numeric(self, other):
        if isinstance(other, Quantity):
            self._check_compatible(other)
            return other.value
        if self.is_dimensionless():
            return float(other)
        raise ValueError(f"Unit discrepancy: cannot compare {self} and {other}")

    def __lt__(self, other):
        return self.value < self._compare_numeric(other)

    def __le__(self, other):
        return self.value <= self._compare_numeric(other)

    def __gt__(self, other):
        return self.value > self._compare_numeric(other)

    def __ge__(self, other):
        return self.value >= self._compare_numeric(other)

    def __eq__(self, other):
        if isinstance(other, Quantity):
            return self.dims == other.dims and self.value == other.value
        if self.is_dimensionless():
            return self.value == float(other)
        return False

    def to_expr(self) -> str:
        # prefer the original hint for non-force dimensions when it matches the quantity dims
        if self.hint:
            try:
                factor, dims = parse_unit_expr(self.hint)
                if dims == self.dims and dims != _FORCE_DIMS and dims != {"m": Fraction(2)}:
                    formatted = format(self.value / factor, f".{PRINT_EXPR_SIGFIGS}g")
                    return f'Q({formatted}, "{self.hint}")'
            except Exception:
                pass
        if self.dims:
            unit_str, divisor = _dims_to_preferred_unit_expr_and_divisor(self.dims, self.value)
            formatted = format(self.value / divisor, f".{PRINT_EXPR_SIGFIGS}g")
            return f'Q({formatted}, "{unit_str}")'
        return str(self.value)

    def __str__(self) -> str:
        # prefer the original hint for non-force dimensions when it matches the quantity dims
        if self.hint:
            try:
                factor, dims = parse_unit_expr(self.hint)
                if dims == self.dims and dims != _FORCE_DIMS and dims != {"m": Fraction(2)}:
                    return f"{_format_number_for_print(self.value / factor)}{self.hint}"
            except Exception:
                pass
        if not self.dims:
            return _format_number_for_print(self.value)
        unit_str, divisor = _dims_to_preferred_unit_expr_and_divisor(self.dims, self.value)
        scaled_value = self.value / divisor
        if self.dims == {"m": Fraction(4)} and unit_str == "mm⁴":
            if abs(scaled_value) >= 0.1e6:
                mantissa = scaled_value / 1e6
                mantissa_str = f"{mantissa:.3f}"
                if "." in mantissa_str:
                    mantissa_str = mantissa_str.rstrip("0").rstrip(".")
                return f"{mantissa_str}e+06{unit_str}"
            return f"{_format_number_for_print(scaled_value)}{unit_str}"
        return f"{_format_number_for_print(scaled_value)}{unit_str}"


def Q(value, unit_expr: str) -> Quantity:
    if isinstance(value, Quantity):
        if not value.is_dimensionless():
            raise ValueError(f"Unit discrepancy: Q(value, unit) value must be dimensionless, got {value}")
        value = value.value
    return Quantity.from_unit(value, unit_expr)


def _is_angle(q: Quantity) -> bool:
    return isinstance(q, Quantity) and q.dims == {"rad": Fraction(1)}


def lin_int(p1, p2, x3):
    x1, y1 = p1
    x2, y2 = p2
    def to_quantity(value):
        return value if isinstance(value, Quantity) else Quantity(float(value), {})
    x1q, x2q, x3q = to_quantity(x1), to_quantity(x2), to_quantity(x3)
    y1q, y2q = to_quantity(y1), to_quantity(y2)
    if x1q.dims != x2q.dims or x1q.dims != x3q.dims:
        raise ValueError(f"Unit discrepancy: lin_int x-values must match units: {x1q}, {x2q}, {x3q}")
    if y1q.dims != y2q.dims:
        raise ValueError(f"Unit discrepancy: lin_int y-values must match units: {y1q} vs {y2q}")
    if x2q.value == x1q.value:
        raise ValueError("lin_int error: x1 and x2 cannot be the same")
    t = (x3q.value - x1q.value) / (x2q.value - x1q.value)
    return Quantity(y1q.value + t * (y2q.value - y1q.value), dict(y1q.dims), y1q.hint or y2q.hint)


# ============================================================
# BUILT-IN FUNCTIONS
# ============================================================

def _require_dimensionless(value, name: str) -> float:
    if isinstance(value, Quantity):
        if not value.is_dimensionless():
            raise ValueError(f"Unit discrepancy: {name}() requires dimensionless input, got {value}")
        return value.value
    return float(value)


def _require_dimensionless_unit_interval(value, name: str) -> float:
    x = _require_dimensionless(value, name)
    if abs(x - 1.0) < 1e-12:
        x = 1.0
    elif abs(x + 1.0) < 1e-12:
        x = -1.0
    if x < -1.0 or x > 1.0:
        raise ValueError(f"Math domain error: {name}() input must be between -1 and 1, got {x}")
    return x


def _require_angle_or_dimensionless(value, name: str) -> float:
    if isinstance(value, Quantity):
        if value.is_dimensionless() or _is_angle(value):
            return value.value
        raise ValueError(f"Unit discrepancy: {name}() requires angle (deg/rad) or dimensionless, got {value}")
    return float(value)


def _flatten_list_args(args):
    if len(args) == 1 and isinstance(args[0], (list, tuple)):
        return list(args[0])
    return list(args)


def q_min(*args):
    values = _flatten_list_args(args)
    if not values:
        raise ValueError("min() expects at least one argument")
    if any(isinstance(v, Quantity) for v in values):
        quantities = [v if isinstance(v, Quantity) else Quantity(float(v), {}) for v in values]
        dims = quantities[0].dims
        for q in quantities[1:]:
            if q.dims != dims:
                raise ValueError(f"Unit discrepancy: min() arguments must have matching units, got {quantities[0]} and {q}")
        minimum = min(quantities, key=lambda q: q.value)
        return Quantity(minimum.value, dict(minimum.dims), None)
    return min(values)


def q_max(*args):
    values = _flatten_list_args(args)
    if not values:
        raise ValueError("max() expects at least one argument")
    if any(isinstance(v, Quantity) for v in values):
        quantities = [v if isinstance(v, Quantity) else Quantity(float(v), {}) for v in values]
        dims = quantities[0].dims
        for q in quantities[1:]:
            if q.dims != dims:
                raise ValueError(f"Unit discrepancy: max() arguments must have matching units, got {quantities[0]} and {q}")
        maximum = max(quantities, key=lambda q: q.value)
        return Quantity(maximum.value, dict(maximum.dims), None)
    return max(values)


def sin(x):
    return math.sin(_require_angle_or_dimensionless(x, "sin"))


def cos(x):
    return math.cos(_require_angle_or_dimensionless(x, "cos"))


def tan(x):
    return math.tan(_require_angle_or_dimensionless(x, "tan"))


def asin(x):
    return Q(math.degrees(math.asin(_require_dimensionless_unit_interval(x, "asin"))), "deg")


def acos(x):
    return Q(math.degrees(math.acos(_require_dimensionless_unit_interval(x, "acos"))), "deg")


def atan(x):
    return Q(math.degrees(math.atan(_require_dimensionless(x, "atan"))), "deg")


def atan2(y, x):
    if isinstance(y, Quantity) or isinstance(x, Quantity):
        yq = y if isinstance(y, Quantity) else Quantity(float(y), {})
        xq = x if isinstance(x, Quantity) else Quantity(float(x), {})
        if yq.dims != xq.dims:
            raise ValueError(f"Unit discrepancy: atan2() requires matching units, got {yq} and {xq}")
        return Q(math.degrees(math.atan2(yq.value, xq.value)), "deg")
    return Q(math.degrees(math.atan2(float(y), float(x))), "deg")


def sqrt(x):
    if isinstance(x, Quantity):
        return x ** 0.5
    return math.sqrt(float(x))


def log(x, base=math.e):
    return math.log(_require_dimensionless(x, "log"), float(base))


def log10(x):
    return math.log10(_require_dimensionless(x, "log10"))


def log2(x):
    return math.log2(_require_dimensionless(x, "log2"))


def exp(x):
    return math.exp(_require_dimensionless(x, "exp"))


def radians(x):
    if isinstance(x, Quantity):
        if _is_angle(x):
            return Q(x.value, "rad")
        raise ValueError(f"Unit discrepancy: radians() expects an angle, got {x}")
    return Q(math.radians(float(x)), "rad")


def degrees(x):
    if isinstance(x, Quantity):
        if _is_angle(x):
            return Q(math.degrees(x.value), "deg")
        raise ValueError(f"Unit discrepancy: degrees() expects an angle, got {x}")
    return Q(math.degrees(float(x)), "deg")


# ============================================================
# PREPROCESSING
# ============================================================

_NUM = r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_NUM_RE = re.compile(_NUM)
_NUM_SPACE_NAME = re.compile(rf"(?<![\w.])({_NUM})\s+([A-Za-z_]\w*)(?!\s*\()")
_UNIT_SCAN_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz°0123456789*/^+-") | set(_SUPERSCRIPTS.keys()) | set(_MUL_SIGNS.keys())


def _replace_caret_power_outside_quotes(expr: str) -> str:
    out = []
    in_quotes = False
    for ch in expr:
        if ch == '"':
            in_quotes = not in_quotes
            out.append(ch)
        elif ch == '^' and not in_quotes:
            out.append('**')
        else:
            out.append(ch)
    return "".join(out)


def replace_number_unit_literals(expr: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(expr):
        match = _NUM_RE.match(expr, i)
        if not match:
            out.append(expr[i])
            i += 1
            continue

        if i > 0 and (expr[i - 1].isalnum() or expr[i - 1] in "_."):
            out.append(expr[i])
            i += 1
            continue

        number = match.group(0)
        j = match.end()
        # if caret immediately follows the number and is an exponent (e.g. 2^2),
        # don't treat it as a unit marker
        if j < len(expr) and expr[j] == "^":
            if j + 1 < len(expr) and (expr[j+1].isdigit() or (expr[j+1] in "+-" and j+2 < len(expr) and expr[j+2].isdigit())):
                out.append(number)
                i = j
                continue
        if j >= len(expr) or expr[j] not in _UNIT_SCAN_CHARS:
            out.append(number)
            i = j
            continue

        end = j
        while end < len(expr) and expr[end] in _UNIT_SCAN_CHARS:
            ch = expr[end]
            if ch in "+-" and not (end > j and expr[end - 1] == "^"):
                break
            end += 1

        best_unit = None
        best_end = j
        for candidate_end in range(end, j, -1):
            candidate = expr[j:candidate_end]
            if candidate.startswith(("*", "·", "×")):
                candidate_unit = candidate[1:]
            else:
                candidate_unit = candidate
            if not candidate_unit:
                continue
            try:
                parse_unit_expr(candidate_unit)
                best_unit = candidate_unit
                best_end = candidate_end
                break
            except Exception:
                continue

        if best_unit is None:
            out.append(number)
            i = j
            continue

        out.append(f'Q({number},"{best_unit}")')
        i = best_end

    return "".join(out)


def preprocess_expr(expr: str) -> str:
    if len(expr) > MAX_EXPR_LEN:
        raise ValueError(f"Expression too long (>{MAX_EXPR_LEN} chars)")
    expr = normalize_text(expr)
    expr = _NUM_SPACE_NAME.sub(r"\1*\2", expr)
    expr = replace_number_unit_literals(expr)
    return _replace_caret_power_outside_quotes(expr)


# ============================================================
# SAFE EVALUATION
# ============================================================

_ALLOWED_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b,
}

_ALLOWED_UNARYOPS = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
}


def _build_allowed_names(context: dict) -> dict[str, object]:
    allowed = {
        "min": q_min,
        "max": q_max,
        "q": Q,
        "Q": Q,
        "lin_int": lin_int,
        "sin": sin,
        "cos": cos,
        "tan": tan,
        "asin": asin,
        "acos": acos,
        "atan": atan,
        "atan2": atan2,
        "sqrt": sqrt,
        "log": log,
        "log10": log10,
        "log2": log2,
        "exp": exp,
        "radians": radians,
        "degrees": degrees,
        "pi": math.pi,
        "e": math.e,
    }
    # standard gravity
    allowed["ge"] = Q(9.81, "m/s^2")
    for name, value in context.items():
        allowed[normalize_identifier(name)] = value
    for name, value in list(allowed.items()):
        allowed.setdefault(name.lower(), value)
        allowed.setdefault(name.upper(), value)
    return allowed


def safe_eval_expr(expr: str, context: dict) -> object:
    expr = expr.strip()
    if not expr:
        raise ValueError("Empty expression")
    expr = preprocess_expr(expr)

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Syntax error in '{expr}': {exc.msg}") from exc

    node_count = 0
    max_depth = 0

    def count_nodes(node: ast.AST, depth: int = 1) -> None:
        nonlocal node_count, max_depth
        node_count += 1
        max_depth = max(max_depth, depth)
        for child in ast.iter_child_nodes(node):
            count_nodes(child, depth + 1)

    count_nodes(tree)
    if node_count > MAX_AST_NODES:
        raise ValueError(f"Expression too complex (>{MAX_AST_NODES} AST nodes)")
    if max_depth > MAX_AST_DEPTH:
        raise ValueError(f"Expression too deep (>{MAX_AST_DEPTH} AST depth)")

    allowed_names = _build_allowed_names(context)

    def eval_node(node: ast.AST):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, bool)):
                return node.value
            raise ValueError(f"Only numeric/bool constants allowed, got {node.value!r}")
        if isinstance(node, ast.Name):
            key = normalize_identifier(node.id)
            if key in allowed_names:
                return allowed_names[key]
            raise ValueError(f"Unknown name: {node.id}")
        if isinstance(node, ast.UnaryOp):
            op = type(node.op)
            if op not in _ALLOWED_UNARYOPS:
                raise ValueError(f"Unary operator not allowed: {op.__name__}")
            return _ALLOWED_UNARYOPS[op](eval_node(node.operand))
        if isinstance(node, ast.BinOp):
            op = type(node.op)
            if op not in _ALLOWED_BINOPS:
                raise ValueError(f"Binary operator not allowed: {op.__name__}")
            return _ALLOWED_BINOPS[op](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only direct function calls are allowed, no attributes.")
            if node.keywords:
                raise ValueError("Keyword arguments are not allowed.")
            func_name = node.func.id
            if func_name == "Q":
                if len(node.args) != 2:
                    raise ValueError('Q() expects exactly 2 args: Q(value, "unit")')
                value = eval_node(node.args[0])
                unit_node = node.args[1]
                if not (isinstance(unit_node, ast.Constant) and isinstance(unit_node.value, str)):
                    raise ValueError('Q() unit must be a quoted string like "kN/m"')
                parse_unit_expr(unit_node.value)
                return Q(value, unit_node.value)
            fn = allowed_names.get(normalize_identifier(func_name))
            if not callable(fn):
                raise ValueError(f"Function not allowed: {func_name}")
            return fn(*(eval_node(arg) for arg in node.args))
        if isinstance(node, ast.Tuple):
            return tuple(eval_node(element) for element in node.elts)
        if isinstance(node, ast.List):
            return [eval_node(element) for element in node.elts]
        raise ValueError(f"Forbidden syntax: {type(node).__name__}")

    return eval_node(tree.body)


# ============================================================
# PRETTY SUBSTITUTION
# ============================================================

_VAR_BOUNDARY = r"(?<![\w]){name}(?![\w])"


def value_to_expr(value: object) -> str:
    if isinstance(value, Quantity):
        return value.to_expr()
    return str(value)


def value_to_pretty(value: object) -> str:
    if isinstance(value, Quantity):
        return str(value)
    if isinstance(value, (int, float)):
        return _format_number_for_print(float(value))
    return str(value)


def _canonicalize_unit_token(unit_token: str) -> str:
    normalized = _normalise_unit_expr(unit_token)
    if not normalized:
        return ""

    out: list[str] = []
    i = 0
    while i < len(normalized):
        ch = normalized[i]
        if ch in "*/":
            out.append(ch)
            i += 1
            continue

        if ch == "°" or ch.isalpha():
            start = i
            while i < len(normalized) and (normalized[i].isalpha() or normalized[i] == "°"):
                i += 1
            chunk = normalized[start:i]
            out.append(UNIT_ALIASES.get(chunk.lower(), chunk))

            if i < len(normalized) and normalized[i] == "^":
                i += 1
                sign = ""
                if i < len(normalized) and normalized[i] in "+-":
                    sign = normalized[i]
                    i += 1
                exp_start = i
                while i < len(normalized) and normalized[i].isdigit():
                    i += 1
                exp = normalized[exp_start:i]
                # convert to superscript digits when possible
                sup_map = {"0":"⁰","1":"¹","2":"²","3":"³","4":"⁴","5":"⁵","6":"⁶","7":"⁷","8":"⁸","9":"⁹","-":"⁻"}
                try:
                    out.append("".join(sup_map[ch] for ch in (sign + exp)))
                except KeyError:
                    out.append(f"^{sign}{exp}")
            elif i < len(normalized) and normalized[i].isdigit():
                exp_start = i
                while i < len(normalized) and normalized[i].isdigit():
                    i += 1
                exp = normalized[exp_start:i]
                if exp == "2":
                    out.append("²")
                elif exp == "3":
                    out.append("³")
                else:
                    sup_map = {"0":"⁰","1":"¹","2":"²","3":"³","4":"⁴","5":"⁵","6":"⁶","7":"⁷","8":"⁸","9":"⁹","-":"⁻"}
                    try:
                        out.append("".join(sup_map[ch] for ch in exp))
                    except KeyError:
                        out.append(f"^{exp}")
            elif i < len(normalized) and normalized[i] in _SUPERSCRIPTS:
                sup = normalized[i]
                i += 1
                if sup == "²":
                    out.append("²")
                elif sup == "³":
                    out.append("³")
                elif sup == "⁻":
                    exp_start = i
                    while i < len(normalized) and normalized[i].isdigit():
                        i += 1
                    exp = normalized[exp_start:i]
                    out.append(f"^-{exp}")
                else:
                    out.append(sup)
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _canonicalize_numeric_unit_literals(expr: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(expr):
        match = _NUM_RE.match(expr, i)
        if not match:
            out.append(expr[i])
            i += 1
            continue

        if i > 0 and (expr[i - 1].isalnum() or expr[i - 1] in "_."):
            out.append(expr[i])
            i += 1
            continue

        number = match.group(0)
        j = match.end()
        if j >= len(expr) or expr[j] not in _UNIT_SCAN_CHARS:
            out.append(number)
            i = j
            continue

        end = j
        while end < len(expr) and expr[end] in _UNIT_SCAN_CHARS:
            ch = expr[end]
            if ch in "+-" and not (end > j and expr[end - 1] == "^"):
                break
            end += 1

        unit_literal = expr[j:end]
        try:
            parse_unit_expr(unit_literal)
            canonical_unit = _canonicalize_unit_token(unit_literal)
            out.append(f"{number}{canonical_unit}")
            i = end
            continue
        except Exception:
            out.append(number)
            i = j
            continue

    return "".join(out)


def pretty_expression(expr: str, context: dict) -> str:
    expr = normalize_text(expr)
    expr = _canonicalize_numeric_unit_literals(expr)
    return _pretty_substitute(expr, context, normalize=False)


def _is_simple_literal_expr(expr: str) -> bool:
    text = expr.strip()
    if re.fullmatch(rf"[+-]?\s*{_NUM}", text):
        return True
    match = re.fullmatch(rf"([+-]?\s*{_NUM})(.+)", text)
    if not match:
        return False
    unit = match.group(2).strip()
    if " " in unit:
        return False
    try:
        parse_unit_expr(unit)
        return True
    except Exception:
        return False


def canonicalize_line_units(text: str) -> str:
    return _canonicalize_numeric_unit_literals(text)


def substitute_variables(expr: str, context: dict) -> str:
    expr = normalize_text(expr)
    norm_ctx = {normalize_identifier(k): v for k, v in context.items()}
    # Allow textual substitution of built-in gravity constant too.
    norm_ctx.setdefault("ge", Q(9.81, "m/s^2"))
    for name in sorted(norm_ctx, key=len, reverse=True):
        expr = re.sub(_VAR_BOUNDARY.format(name=re.escape(name)), value_to_expr(norm_ctx[name]), expr, flags=re.IGNORECASE)
    return expr


def _pretty_substitute(expr: str, context: dict, normalize: bool = True) -> str:
    if normalize:
        expr = normalize_text(expr)
    norm_ctx = {normalize_identifier(k): v for k, v in context.items()}
    # Allow pretty substitution of built-in gravity constant too.
    norm_ctx.setdefault("ge", Q(9.81, "m/s^2"))
    for name in sorted(norm_ctx, key=len, reverse=True):
        replacement = value_to_pretty(norm_ctx[name])
        unit_bearing = bool(re.search(r"[A-Za-z°]", replacement))
        pattern = re.compile(_VAR_BOUNDARY.format(name=re.escape(name)), flags=re.IGNORECASE)
        def replace(match):
            if unit_bearing:
                end = match.end()
                if expr[end:end+2] == "**" or (end < len(expr) and expr[end] == "^") or (end < len(expr) and expr[end] in _SUPERSCRIPTS):
                    return f"({replacement})"
            return replacement
        expr = pattern.sub(replace, expr)
    return expr


def pretty_substitute(expr: str, context: dict) -> str:
    return _pretty_substitute(expr, context, normalize=True)


# ============================================================
# LINE PROCESSING
# ============================================================

ASSIGN_RE = re.compile(r"^(\s*[^=\s]+)(\s*=\s*)(.*)$")
TRAILING_EQ_RE = re.compile(r"^(.*?)(\s*=\s*)$")
TRAILING_EQ_UNIT_RE = re.compile(r"^(.*?)(\s*=\s*)\(\s*(.+?)\s*\)\s*$")


def _normalize_assignment_separator(separator: str) -> str:
    return " = " if "=" in separator else separator


def _apply_requested_unit(value: object, unit_expr: str) -> object:
    factor, dims = parse_unit_expr(unit_expr)
    hint = _canonicalize_unit_token(unit_expr) if dims else None
    if isinstance(value, Quantity):
        if value.dims != dims:
            # Bridge equivalent force dimensions: kg*m/s^2 <-> N-family.
            if value.dims == _FORCE_DIMS and dims == {"N": Fraction(1)}:
                return Quantity(value.value, {"N": Fraction(1)}, hint=hint or unit_expr)
            raise ValueError(f"Unit discrepancy: requested output unit {hint or unit_expr} is incompatible with {value}")
        if hint:
            return Quantity(value.value, dict(value.dims), hint=hint)
        return value
    if dims:
        return Quantity.from_unit(float(value), hint or unit_expr)
    return float(value)


def _canonicalize_assignment_chain(lhs_raw: str, separator: str, rhs_raw: str, context: dict[str, object]) -> str:
    parts = [part.strip() for part in rhs_raw.split("=")]
    if not parts:
        return f"{lhs_raw}{separator}{rhs_raw}"
    lhs_name = lhs_raw.strip()
    expr = parts[0]
    if expr and _is_valid_var_name(lhs_name):
        try:
            value = safe_eval_expr(substitute_variables(expr, context), context)
            context[lhs_name] = value
        except Exception:
            pass
    final_part = parts[-1]
    # If final part is a requested unit in parentheses, evaluate and store value with that hint
    m = re.fullmatch(r"\(\s*(.+?)\s*\)", final_part)
    if m:
        unit_expr = m.group(1)
        try:
            parse_unit_expr(unit_expr)
        except Exception:
            # not a valid unit, fall through
            unit_expr = None
        if unit_expr:
            try:
                expr_val = safe_eval_expr(substitute_variables(parts[0], context), context)
            except Exception:
                expr_val = None
            if expr_val is not None:
                if isinstance(expr_val, Quantity):
                    hint = _canonicalize_unit_token(unit_expr)
                    context[lhs_name] = Quantity(expr_val.value, expr_val.dims, hint=hint)
                    pretty_mid = pretty_expression(parts[0], context)
                    return f"{lhs_raw}{separator}{pretty_mid} = {value_to_pretty(context[lhs_name])}"
                else:
                    context[lhs_name] = expr_val
                    pretty_mid = pretty_expression(parts[0], context)
                    return f"{lhs_raw}{separator}{pretty_mid} = {value_to_pretty(expr_val)}"
    if _is_simple_literal_expr(final_part):
        orig_expr = canonicalize_line_units(normalize_text(parts[0])) if parts[0] else ""
        pretty_expr = pretty_expression(parts[0], context) if parts[0] else ""
        pretty_final = pretty_expression(final_part, context)
        chain: list[str] = []
        if orig_expr:
            chain.append(orig_expr)
        if pretty_expr and pretty_expr != orig_expr:
            chain.append(pretty_expr)
        chain.append(pretty_final)
        return f"{lhs_raw}{separator}{' = '.join(chain)}"
    canonical_parts = [pretty_expression(part, context) if part else "" for part in parts]
    if len(canonical_parts) >= 3 and canonical_parts[0] == canonical_parts[1]:
        canonical_parts.pop(1)
    return f"{lhs_raw}{separator}{' = '.join(canonical_parts)}"


def process_lines(text: str) -> str:
    global LAST_EVAL_LINE
    lines = text.splitlines()
    context: dict[str, object] = {}
    output_lines: list[str] = []

    for raw in lines:
        LAST_EVAL_LINE = raw
        norm_raw = normalize_text(raw)
        requested_unit_expr: str | None = None
        trailing_unit_match = TRAILING_EQ_UNIT_RE.match(norm_raw)
        if trailing_unit_match:
            requested_unit_expr = trailing_unit_match.group(3)
            parse_unit_expr(requested_unit_expr)
            norm_raw = f"{trailing_unit_match.group(1)}{trailing_unit_match.group(2)}"
        canonical_raw = canonicalize_line_units(norm_raw)
        stripped = norm_raw.strip()
        if not stripped:
            output_lines.append("")
            continue
        if stripped.startswith("#"):
            output_lines.append(raw)
            continue

        eq_count = stripped.count("=")
        if eq_count == 1 and stripped.endswith("="):
            match = TRAILING_EQ_RE.match(norm_raw)
            if not match:
                output_lines.append(raw)
                continue
            expr_raw = match.group(1)
            expr = expr_raw.strip()
            if not expr:
                output_lines.append(canonical_raw)
                continue
            eval_expr = substitute_variables(expr, context)
            value = safe_eval_expr(eval_expr, context)
            if requested_unit_expr:
                value = _apply_requested_unit(value, requested_unit_expr)
            orig_expr = canonicalize_line_units(normalize_text(expr))
            pretty_mid = pretty_expression(expr, context)
            suffix = "" if canonical_raw.endswith(" ") else " "
            if pretty_mid and pretty_mid != orig_expr:
                output_lines.append(f"{canonical_raw}{suffix}{pretty_mid} = {value_to_pretty(value)}")
            else:
                output_lines.append(f"{canonical_raw}{suffix}{value_to_pretty(value)}")
            continue

        if eq_count >= 2:
            match = ASSIGN_RE.match(norm_raw)
            if match:
                lhs_raw = match.group(1)
                separator = match.group(2)
                rhs_raw = match.group(3)
                lhs_name = lhs_raw.strip()
                if rhs_raw.rstrip().endswith("="):
                    trailing_match = TRAILING_EQ_RE.match(rhs_raw)
                    if trailing_match:
                        expr_clean = trailing_match.group(1).strip()
                        if expr_clean and trailing_match.group(1).count("=") == 0 and _is_valid_var_name(lhs_name):
                            value = safe_eval_expr(substitute_variables(expr_clean, context), context)
                            if requested_unit_expr:
                                value = _apply_requested_unit(value, requested_unit_expr)
                            context[lhs_name] = value
                            pretty_mid = pretty_expression(expr_clean, context)
                            suffix = "" if canonical_raw.endswith(" ") else " "
                            # If RHS is a simple variable or simple literal, avoid printing the evaluated value twice.
                            if _is_valid_var_name(expr_clean):
                                output_lines.append(f"{lhs_raw}{separator}{expr_clean} = {value_to_pretty(value)}")
                            elif _is_simple_literal_expr(expr_clean):
                                # show canonical RHS once
                                canonical_rhs = pretty_expression(expr_clean, context)
                                output_lines.append(f"{lhs_raw}{separator}{canonical_rhs}")
                            else:
                                orig_expr = canonicalize_line_units(normalize_text(expr_clean))
                                chain: list[str] = []
                                if pretty_mid and pretty_mid != orig_expr:
                                    chain.append(pretty_mid)
                                chain.append(value_to_pretty(value))
                                output_lines.append(f"{canonical_raw}{suffix}{' = '.join(chain)}")
                            continue
                if "=" in rhs_raw:
                    output_lines.append(_canonicalize_assignment_chain(lhs_raw, separator, rhs_raw, context))
                    continue
            output_lines.append(raw)
            if eq_count >= 1 and norm_raw.split("=")[0].strip() and _is_valid_var_name(norm_raw.split("=")[0].strip()):
                parts = [part.strip() for part in stripped.split("=")]
                if len(parts) >= 2:
                    rhs = parts[-1]
                    try:
                        context[parts[0]] = safe_eval_expr(rhs, context)
                    except Exception:
                        pass
            continue

        if eq_count == 1 and "=" in stripped:
            match = ASSIGN_RE.match(norm_raw)
            if not match:
                output_lines.append(raw)
                continue
            lhs_raw, separator, rhs_raw = match.groups()
            lhs_name = lhs_raw.strip()
            rhs_value = rhs_raw.strip()
            if _is_valid_var_name(lhs_name) and rhs_value:
                try:
                    value = safe_eval_expr(substitute_variables(rhs_value, context), context)
                    context[lhs_name] = value
                    if _is_simple_literal_expr(rhs_value):
                        canonical_rhs = pretty_expression(rhs_value, context)
                        output_lines.append(f"{lhs_raw}{separator}{canonical_rhs}")
                    else:
                        output_lines.append(raw)
                except Exception:
                    output_lines.append(raw)
            else:
                output_lines.append(raw)
            continue

        output_lines.append(raw)
    return "\n".join(output_lines)


def _is_valid_var_name(name: str) -> bool:
    if not name or re.search(r"\s|=", name):
        return False
    if re.search(r"[+\-*/^(){}\[\],:<>]", name):
        return False
    if re.match(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)", name):
        return False
    return True


# ============================================================
# CLIPBOARD + MAIN
# ============================================================

def main() -> None:
    global LAST_EVAL_LINE
    if pyperclip is None:
        raise RuntimeError("pyperclip is not available")
    original = pyperclip.paste()
    try:
        result = process_lines(original.strip("\n"))
    except Exception as error:
        line_info = f" ({LAST_EVAL_LINE})" if LAST_EVAL_LINE else ""
        result = original + f"\n[Error during evaluation: {error}{line_info}]"
    pyperclip.copy(result)
    time.sleep(PASTE_DELAY_S)
    if AUTO_PASTE:
        if pyautogui is None:
            raise RuntimeError("pyautogui is not available")
        pyautogui.hotkey(*PASTE_KEYS)


if __name__ == "__main__":
    main()
