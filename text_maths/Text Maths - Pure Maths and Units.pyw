"""
Clipboard engineering calculator.

Select text, run the script, and every line that ends in "=" is evaluated
in place. No variables, units supported.

    5m+5m=m     ->  5m+5m= 10m
    5mm+5mm=    ->  5mm+5mm= 0.01m
    5+5=        ->  5+5= 10
"""

import ast
import math
import re
import time
from fractions import Fraction

import pyautogui
import pyperclip

# ============================================================
# SETTINGS
# ============================================================

AUTO_PASTE = True
PASTE_KEYS = ("ctrl", "v")
PASTE_DELAY_S = 0.01
DECIMALS = 3

# ============================================================
# DIMENSIONS  (mass, length, time, angle)
# ============================================================

F = Fraction
NONE_D = (F(0), F(0), F(0), F(0))
MASS = (F(1), F(0), F(0), F(0))
LENGTH = (F(0), F(1), F(0), F(0))
TIME = (F(0), F(0), F(1), F(0))
ANGLE = (F(0), F(0), F(0), F(1))
FORCE = (F(1), F(1), F(-2), F(0))
PRESSURE = (F(1), F(-1), F(-2), F(0))
FORCE_PER_LEN = (F(1), F(0), F(-2), F(0))
MOMENT = (F(1), F(2), F(-2), F(0))
AREA = (F(0), F(2), F(0), F(0))
VOLUME = (F(0), F(3), F(0), F(0))
INERTIA = (F(0), F(4), F(0), F(0))


def d_add(a, b, sign=1):
    return (a[0] + sign * b[0], a[1] + sign * b[1],
            a[2] + sign * b[2], a[3] + sign * b[3])


def d_mul(a, n):
    return (a[0] * n, a[1] * n, a[2] * n, a[3] * n)


DIM_NAMES = {
    NONE_D: "a plain number", MASS: "mass", LENGTH: "length", TIME: "time",
    ANGLE: "an angle", FORCE: "force", PRESSURE: "pressure",
    FORCE_PER_LEN: "force per length", MOMENT: "moment", AREA: "area",
    VOLUME: "volume", INERTIA: "second moment of area",
}


def dim_name(dims):
    return DIM_NAMES.get(dims, f"units of {base_unit_text(dims)}")


# ============================================================
# UNITS
# ============================================================

# name: (factor to base SI, dimensions, printed symbol)
UNITS = {
    "N": (1.0, FORCE, "N"), "kN": (1e3, FORCE, "kN"), "MN": (1e6, FORCE, "MN"),
    "g": (1e-3, MASS, "g"), "kg": (1.0, MASS, "kg"), "t": (1e3, MASS, "t"),
    "mm": (1e-3, LENGTH, "mm"), "cm": (1e-2, LENGTH, "cm"),
    "m": (1.0, LENGTH, "m"), "km": (1e3, LENGTH, "km"),
    "in": (0.0254, LENGTH, "in"), "ft": (0.3048, LENGTH, "ft"),
    "s": (1.0, TIME, "s"), "min": (60.0, TIME, "min"), "hr": (3600.0, TIME, "hr"),
    "Pa": (1.0, PRESSURE, "Pa"), "kPa": (1e3, PRESSURE, "kPa"),
    "MPa": (1e6, PRESSURE, "MPa"), "GPa": (1e9, PRESSURE, "GPa"),
    "psi": (6894.757293168, PRESSURE, "psi"),
    "rad": (1.0, ANGLE, "rad"),
    "deg": (math.pi / 180.0, ANGLE, "°"), "°": (math.pi / 180.0, ANGLE, "°"),
}

# Longest first so "mm" wins over "m", "MPa" over "MN" etc.
UNIT_NAMES = sorted(UNITS, key=len, reverse=True)

SUP_IN = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
SUP_OUT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"


def parse_unit(text):
    """Return (factor, dims, symbol). Raises ValueError if not a valid unit."""
    text = (text.strip()
            .replace(" ", "").replace("·", "*").replace("×", "*")
            .replace("⋅", "*"))
    if not text:
        return 1.0, NONE_D, ""

    factor, dims, out = 1.0, NONE_D, []
    pos, sign, need_unit = 0, 1, True

    while pos < len(text):
        char = text[pos]

        if char in "*/":
            if need_unit:
                raise ValueError(f"bad unit '{text}'")
            sign = 1 if char == "*" else -1
            out.append(char)
            pos += 1
            need_unit = True
            continue

        name = next((n for n in UNIT_NAMES if text.startswith(n, pos)), None)
        if name is None:
            raise ValueError(f"unknown unit '{text[pos:]}'")
        pos += len(name)

        power = 1
        if pos < len(text) and text[pos] == "^":
            match = re.match(r"[+-]?\d+", text[pos + 1:])
            if not match:
                raise ValueError(f"bad exponent in '{text}'")
            power = int(match.group())
            pos += 1 + len(match.group())
        elif pos < len(text) and text[pos] in SUPERSCRIPTS:
            start = pos
            while pos < len(text) and text[pos] in SUPERSCRIPTS:
                pos += 1
            power = int(text[start:pos].translate(SUP_IN))
        elif pos < len(text) and text[pos].isdigit():
            start = pos
            while pos < len(text) and text[pos].isdigit():
                pos += 1
            power = int(text[start:pos])

        unit_factor, unit_dims, symbol = UNITS[name]
        factor *= unit_factor ** (sign * power)
        dims = d_add(dims, d_mul(unit_dims, F(sign * power)))
        out.append(symbol + (str(power).translate(SUP_OUT) if power != 1 else ""))
        need_unit = False

    if need_unit:
        raise ValueError(f"bad unit '{text}'")
    return factor, dims, "".join(out)


def base_unit_text(dims):
    """Fallback display, e.g. m/s or kg*m²/s³."""
    top, bottom = [], []
    for symbol, power in zip(("kg", "m", "s", "rad"), dims):
        if power == 0:
            continue
        size = abs(power)
        text = symbol if size == 1 else (
            symbol + str(size.numerator).translate(SUP_OUT)
            if size.denominator == 1
            else f"{symbol}^{size.numerator}/{size.denominator}")
        (top if power > 0 else bottom).append(text)
    result = "*".join(top) or "1"
    return result + ("/" + "*".join(bottom) if bottom else "")


# ============================================================
# QUANTITY
# ============================================================

class Quantity:
    __slots__ = ("value", "dims")

    def __init__(self, value, dims=NONE_D):
        self.value = float(value)
        self.dims = dims

    def __repr__(self):
        return f"Quantity({self.value}, {base_unit_text(self.dims)})"

    @staticmethod
    def of(value):
        return value if isinstance(value, Quantity) else Quantity(value)

    def _match(self, other, what):
        other = Quantity.of(other)
        if self.dims != other.dims:
            raise ValueError(
                f"unit mismatch: cannot {what} {dim_name(self.dims)} "
                f"and {dim_name(other.dims)}")
        return other

    def __add__(self, other):
        other = self._match(other, "add")
        return Quantity(self.value + other.value, self.dims)

    __radd__ = __add__

    def __sub__(self, other):
        other = self._match(other, "subtract")
        return Quantity(self.value - other.value, self.dims)

    def __rsub__(self, other):
        return Quantity.of(other).__sub__(self)

    def __mul__(self, other):
        other = Quantity.of(other)
        return Quantity(self.value * other.value, d_add(self.dims, other.dims))

    __rmul__ = __mul__

    def __truediv__(self, other):
        other = Quantity.of(other)
        return Quantity(self.value / other.value,
                        d_add(self.dims, other.dims, -1))

    def __rtruediv__(self, other):
        return Quantity.of(other).__truediv__(self)

    def __pow__(self, power):
        power = Quantity.of(power)
        if power.dims != NONE_D:
            raise ValueError("unit mismatch: the exponent must be a plain number")
        exact = Fraction(power.value).limit_denominator(100)
        return Quantity(self.value ** power.value, d_mul(self.dims, exact))

    def __rpow__(self, other):
        return Quantity.of(other).__pow__(self)

    def __neg__(self):
        return Quantity(-self.value, self.dims)

    def __pos__(self):
        return self


def Q(value, unit_text):
    factor, dims, _ = parse_unit(unit_text)
    return Quantity(Quantity.of(value).value * factor, dims)


# ============================================================
# FUNCTIONS
# ============================================================

def plain(value, name):
    value = Quantity.of(value)
    if value.dims != NONE_D:
        raise ValueError(f"{name}() needs a plain number, got {dim_name(value.dims)}")
    return value.value


def angle(value, name):
    value = Quantity.of(value)
    if value.dims in (ANGLE, NONE_D):
        return value.value
    raise ValueError(f"{name}() needs an angle, got {dim_name(value.dims)}")


def same_dims(values, name):
    values = [Quantity.of(v) for v in values]
    if not values:
        raise ValueError(f"{name}() needs at least one value")
    if any(v.dims != values[0].dims for v in values):
        raise ValueError(f"unit mismatch: {name}() values must share the same units")
    return values


def spread(values):
    if len(values) == 1 and isinstance(values[0], (list, tuple)):
        return list(values[0])
    return list(values)


def fn_min(*values):
    return min(same_dims(spread(values), "min"), key=lambda v: v.value)


def fn_max(*values):
    return max(same_dims(spread(values), "max"), key=lambda v: v.value)


def lin_int(point1, point2, x3):
    (x1, y1), (x2, y2) = point1, point2
    x1, x2, x3 = same_dims([x1, x2, x3], "lin_int")
    y1, y2 = same_dims([y1, y2], "lin_int")
    if x1.value == x2.value:
        raise ValueError("lin_int(): the two x values cannot be equal")
    ratio = (x3.value - x1.value) / (x2.value - x1.value)
    return Quantity(y1.value + ratio * (y2.value - y1.value), y1.dims)


def fn_atan2(y, x):
    y, x = same_dims([y, x], "atan2")
    return Quantity(math.atan2(y.value, x.value), ANGLE)


def fn_sqrt(value):
    value = Quantity.of(value)
    if value.value < 0:
        raise ValueError("cannot take the square root of a negative value")
    return value ** 0.5


def fn_abs(value):
    value = Quantity.of(value)
    return Quantity(abs(value.value), value.dims)


def fn_round(value, places=0):
    value = Quantity.of(value)
    return Quantity(round(value.value, int(plain(places, "round"))), value.dims)


FUNCTIONS = {
    "min": fn_min, "max": fn_max, "lin_int": lin_int,
    "abs": fn_abs, "round": fn_round, "sqrt": fn_sqrt,
    "sin": lambda x: math.sin(angle(x, "sin")),
    "cos": lambda x: math.cos(angle(x, "cos")),
    "tan": lambda x: math.tan(angle(x, "tan")),
    "asin": lambda x: Quantity(math.asin(plain(x, "asin")), ANGLE),
    "acos": lambda x: Quantity(math.acos(plain(x, "acos")), ANGLE),
    "atan": lambda x: Quantity(math.atan(plain(x, "atan")), ANGLE),
    "atan2": fn_atan2,
    "log": lambda x, base=math.e: math.log(plain(x, "log"), plain(base, "log")),
    "log10": lambda x: math.log10(plain(x, "log10")),
    "log2": lambda x: math.log2(plain(x, "log2")),
    "exp": lambda x: math.exp(plain(x, "exp")),
    "radians": lambda x: Quantity(angle(x, "radians"), ANGLE),
    "degrees": lambda x: Quantity(angle(x, "degrees"), ANGLE),
}

CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "ge": Q(9.81, "m/s^2"),
}

# ============================================================
# PREPROCESSING  (turn "5mm" into Q(5,"mm"))
# ============================================================

NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
TIDY = str.maketrans({"×": "*", "÷": "/", "−": "-", "–": "-", "—": "-",
                      "·": "*", "⋅": "*", "π": "pi"})
STOP_CHARS = set("+-,()[]=<> ")


def preprocess(text):
    """Quote unit literals, then turn ^ into ** outside those quotes."""
    text = text.translate(TIDY)
    out, i = [], 0

    while i < len(text):
        match = NUMBER.match(text, i)
        if not match or (i and (text[i - 1].isalnum() or text[i - 1] in "_.")):
            out.append("**" if text[i] == "^" else text[i])
            i += 1
            continue

        number, start = match.group(), match.end()

        # Take the longest run of characters that still parses as a unit.
        end = start
        while end < len(text) and text[end] not in STOP_CHARS:
            end += 1

        unit = None
        while end > start:
            try:
                parse_unit(text[start:end])
                unit = text[start:end]
                break
            except ValueError:
                end -= 1

        if unit:
            out.append(f'Q({number},"{unit}")')
            i = end
        else:
            out.append(number)
            i = start

    return "".join(out)


# ============================================================
# SAFE EVALUATION
# ============================================================

BINARY = {
    ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b,
}
UNARY = {ast.UAdd: lambda a: +a, ast.USub: lambda a: -a}


class NotASum(Exception):
    """The line is ordinary text, not a calculation."""


def evaluate(node):
    kind = type(node)

    if kind is ast.Constant:
        if isinstance(node.value, (int, float, str)) and not isinstance(node.value, bool):
            return node.value

    elif kind is ast.Name:
        if node.id.casefold() in CONSTANTS:
            return CONSTANTS[node.id.casefold()]
        raise NotASum(f"unknown name '{node.id}'")

    elif kind is ast.UnaryOp and type(node.op) in UNARY:
        return UNARY[type(node.op)](evaluate(node.operand))

    elif kind is ast.BinOp and type(node.op) in BINARY:
        return BINARY[type(node.op)](evaluate(node.left), evaluate(node.right))

    elif kind is ast.Call and type(node.func) is ast.Name and not node.keywords:
        name = node.func.id.casefold()
        args = [evaluate(a) for a in node.args]
        if name == "q":
            return Q(*args)
        if name in FUNCTIONS:
            return FUNCTIONS[name](*args)
        raise NotASum(f"unknown function '{node.func.id}'")

    elif kind in (ast.Tuple, ast.List):
        return [evaluate(item) for item in node.elts]

    raise NotASum("that expression is not allowed")


def calculate(expression):
    if len(expression) > 10_000:
        raise ValueError("expression is too long")
    try:
        tree = ast.parse(preprocess(expression), mode="eval")
    except SyntaxError:
        raise NotASum("cannot read that expression") from None
    return Quantity.of(evaluate(tree.body))


# ============================================================
# OUTPUT
# ============================================================

def show_number(value):
    if not math.isfinite(value):
        return str(value)
    if value == 0:
        return "0"
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    if abs(value) >= 1e6 or abs(value) < 1e-3:
        mantissa, exponent = f"{value:.3e}".split("e")
        return f"{mantissa.rstrip('0').rstrip('.')}e{int(exponent)}"
    return f"{value:.{DECIMALS}f}".rstrip("0").rstrip(".")


def show_in(quantity, unit_text):
    factor, dims, symbol = parse_unit(unit_text)
    if quantity.dims != dims:
        raise ValueError(
            f"unit mismatch: the answer is {dim_name(quantity.dims)}, "
            f"but {symbol or 'a plain number'} was asked for")
    return show_number(quantity.value / factor) + symbol


AUTO_UNITS = {
    FORCE: "kN", FORCE_PER_LEN: "kN/m", MOMENT: "kNm", LENGTH: "m",
    AREA: "mm^2", VOLUME: "m^3", INERTIA: "mm^4", MASS: "kg",
    TIME: "s", ANGLE: "deg",
}


def show_auto(quantity):
    if quantity.dims == NONE_D:
        return show_number(quantity.value)
    if quantity.dims == PRESSURE:
        return show_in(quantity, "kPa" if abs(quantity.value) < 1e6 else "MPa")
    if quantity.dims in AUTO_UNITS:
        return show_in(quantity, AUTO_UNITS[quantity.dims])
    return show_number(quantity.value) + base_unit_text(quantity.dims)


# ============================================================
# LINE HANDLING
# ============================================================

# number, then anything left over (a previously pasted answer)
OLD_ANSWER = re.compile(r"^\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(.*)$")


def read_line(line):
    """Return (before_equals, expression, wanted_unit) or None if not a sum."""
    body = line.rstrip()
    if "=" not in body:
        return None

    cut = body.rfind("=")
    expression, tail = body[:cut].strip(), body[cut + 1:].strip()
    if not expression or "=" in expression:
        return None

    if not tail:
        return body[:cut + 1], expression, None

    try:                                    # "= mm"  -> convert to mm
        parse_unit(tail)
        return body[:cut + 1], expression, tail
    except ValueError:
        pass

    match = OLD_ANSWER.match(tail)          # "= 10m" -> an old answer, redo it
    if match:
        leftover = match.group(1).strip()
        if not leftover:
            return body[:cut + 1], expression, None
        try:
            parse_unit(leftover)
            return body[:cut + 1], expression, leftover
        except ValueError:
            pass

    return None                             # ordinary prose, leave it alone


def process_line(line):
    parts = read_line(line)
    if parts is None:
        return line
    head, expression, wanted = parts
    try:
        answer = calculate(expression)
        return f"{head} {show_in(answer, wanted) if wanted else show_auto(answer)}"
    except NotASum:
        return line                      # ordinary text, leave it exactly as it is
    except Exception as error:
        return f"{line.rstrip()} [{error}]"


def process_text(text):
    out = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        out.append(process_line(body) + line[len(body):])
    return "".join(out)


# ============================================================
# CLIPBOARD AND AUTO-PASTE
# ============================================================

def main():
    original_text = pyperclip.paste()
    result = process_text(original_text)

    pyperclip.copy(result)

    if AUTO_PASTE:
        if PASTE_DELAY_S:
            time.sleep(PASTE_DELAY_S)

        pyautogui.hotkey(*PASTE_KEYS)


if __name__ == "__main__":
    main()
