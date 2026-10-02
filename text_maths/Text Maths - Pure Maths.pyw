import ast
import math
import time

import pyautogui
import pyperclip


# ============================================================
# SETTINGS
# ============================================================

AUTO_PASTE = True
PASTE_KEYS = ("ctrl", "v")
PASTE_DELAY_S = 0.01

DECIMAL_PLACES = 3

MAX_EXPR_LEN = 50_000
MAX_AST_NODES = 20_000
MAX_AST_DEPTH = 400


# ============================================================
# RESULT FORMATTING
# ============================================================

def format_number(value) -> str:
    value = float(value)

    if not math.isfinite(value):
        return str(value)

    if value == 0:
        return "0"

    if value.is_integer():
        return str(int(value))

    absolute_value = abs(value)

    if absolute_value >= 1e6:
        mantissa, exponent = f"{value:.3e}".split("e")
        return f"{mantissa.rstrip('0').rstrip('.')}e{exponent}"

    if absolute_value < 0.1:
        return f"{value:.3g}"

    return f"{value:.{DECIMAL_PLACES}f}".rstrip("0").rstrip(".")


# ============================================================
# CUSTOM FUNCTIONS
# ============================================================

def lin_int(p1, p2, x3):
    x1, y1 = p1
    x2, y2 = p2

    if x1 == x2:
        raise ValueError("lin_int(): x1 and x2 cannot be equal")

    return y1 + (x3 - x1) * (y2 - y1) / (x2 - x1)


def minimum(*values):
    if len(values) == 1 and isinstance(values[0], (list, tuple)):
        values = values[0]

    if not values:
        raise ValueError("min() requires at least one value")

    return min(values)


def maximum(*values):
    if len(values) == 1 and isinstance(values[0], (list, tuple)):
        values = values[0]

    if not values:
        raise ValueError("max() requires at least one value")

    return max(values)


def asin_degrees(value):
    return math.degrees(math.asin(value))


def acos_degrees(value):
    return math.degrees(math.acos(value))


def atan_degrees(value):
    return math.degrees(math.atan(value))


def atan2_degrees(y, x):
    return math.degrees(math.atan2(y, x))


# Local dictionaries make AST lookup quick.
FUNCTIONS = {
    "min": minimum,
    "max": maximum,
    "lin_int": lin_int,

    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,

    "asin": asin_degrees,
    "acos": acos_degrees,
    "atan": atan_degrees,
    "atan2": atan2_degrees,

    "sqrt": math.sqrt,

    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,

    "radians": math.radians,
    "degrees": math.degrees,
}

CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "ge": 9.81,
}


# ============================================================
# OPERATOR FUNCTIONS
# ============================================================

def add(left, right):
    return left + right


def subtract(left, right):
    return left - right


def multiply(left, right):
    return left * right


def divide(left, right):
    return left / right


def power(left, right):
    return left ** right


def positive(value):
    return +value


def negative(value):
    return -value


BINARY_OPERATORS = {
    ast.Add: add,
    ast.Sub: subtract,
    ast.Mult: multiply,
    ast.Div: divide,
    ast.Pow: power,
}

UNARY_OPERATORS = {
    ast.UAdd: positive,
    ast.USub: negative,
}


# ============================================================
# EXPRESSION NORMALISATION
# ============================================================

TRANSLATION_TABLE = str.maketrans({
    "×": "*",
    "÷": "/",
    "−": "-",
    "–": "-",
    "—": "-",
    "∗": "*",
    "＊": "*",
    "·": "*",
    "⋅": "*",
    "⋆": "*",
    "π": "pi",
    "Π": "pi",
})


def normalize_expression(expression: str) -> str:
    return expression.translate(TRANSLATION_TABLE).replace("^", "**").strip()


# ============================================================
# SAFE EVALUATION
# ============================================================

def safe_eval(expression: str):
    if len(expression) > MAX_EXPR_LEN:
        raise ValueError(
            f"Expression exceeds {MAX_EXPR_LEN} characters"
        )

    expression = normalize_expression(expression)

    if not expression:
        raise ValueError("Empty expression")

    try:
        root = ast.parse(expression, mode="eval").body
    except SyntaxError as error:
        raise ValueError(f"Syntax error: {error.msg}") from error

    node_count = 0

    def evaluate(node, depth=1):
        nonlocal node_count

        node_count += 1

        if node_count > MAX_AST_NODES:
            raise ValueError(
                f"Expression exceeds {MAX_AST_NODES} syntax nodes"
            )

        if depth > MAX_AST_DEPTH:
            raise ValueError(
                f"Expression exceeds a depth of {MAX_AST_DEPTH}"
            )

        node_type = type(node)

        if node_type is ast.Constant:
            value = node.value

            if type(value) not in (int, float):
                raise ValueError("Only numbers are allowed")

            return value

        if node_type is ast.Name:
            name = node.id.casefold()

            try:
                return CONSTANTS[name]
            except KeyError:
                raise ValueError(f"Unknown name: {node.id}") from None

        if node_type is ast.UnaryOp:
            function = UNARY_OPERATORS.get(type(node.op))

            if function is None:
                raise ValueError(
                    f"Operator is not allowed: {type(node.op).__name__}"
                )

            return function(evaluate(node.operand, depth + 1))

        if node_type is ast.BinOp:
            function = BINARY_OPERATORS.get(type(node.op))

            if function is None:
                raise ValueError(
                    f"Operator is not allowed: {type(node.op).__name__}"
                )

            return function(
                evaluate(node.left, depth + 1),
                evaluate(node.right, depth + 1),
            )

        if node_type is ast.Call:
            if type(node.func) is not ast.Name:
                raise ValueError("Only direct function calls are allowed")

            if node.keywords:
                raise ValueError("Keyword arguments are not allowed")

            function_name = node.func.id.casefold()
            function = FUNCTIONS.get(function_name)

            if function is None:
                raise ValueError(
                    f"Function is not allowed: {node.func.id}"
                )

            arguments = [
                evaluate(argument, depth + 1)
                for argument in node.args
            ]

            return function(*arguments)

        if node_type is ast.Tuple:
            return tuple(
                evaluate(element, depth + 1)
                for element in node.elts
            )

        if node_type is ast.List:
            return [
                evaluate(element, depth + 1)
                for element in node.elts
            ]

        raise ValueError(
            f"Syntax is not allowed: {node_type.__name__}"
        )

    return evaluate(root)


# ============================================================
# TEXT PROCESSING
# ============================================================

def process_line(line: str) -> str:
    trimmed_line = line.rstrip()

    if not trimmed_line.endswith("="):
        return line

    expression = trimmed_line[:-1].strip()

    if not expression:
        return line

    try:
        result = format_number(safe_eval(expression))
        return f"{line} {result}"
    except Exception as error:
        return f"{line} [Error: {error}]"


def process_text(text: str) -> str:
    lines = text.splitlines(keepends=True)

    # splitlines() returns nothing for an empty string.
    if not lines:
        return text

    output = []

    for line in lines:
        if line.endswith("\r\n"):
            output.append(process_line(line[:-2]) + "\r\n")
        elif line.endswith(("\n", "\r")):
            output.append(process_line(line[:-1]) + line[-1])
        else:
            output.append(process_line(line))

    return "".join(output)


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