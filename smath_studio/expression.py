"""Expression AST and postfix-to-tree conversion for SMath Studio math regions."""

from __future__ import annotations

import math
import operator as op_module
from dataclasses import dataclass, field
from typing import Any, Optional
from xml.etree.ElementTree import Element


# ---------------------------------------------------------------------------
# AST node hierarchy
# ---------------------------------------------------------------------------

class ASTNode:
    """Base class for all expression tree nodes."""

    def evaluate(self, context: "EvalContext") -> Any:
        raise NotImplementedError(f"{type(self).__name__}.evaluate")

    def children(self) -> list["ASTNode"]:
        return []


@dataclass
class Number(ASTNode):
    value: float

    def evaluate(self, context):
        return self.value

    def __repr__(self):
        return f"Number({self.value})"


@dataclass
class StringLiteral(ASTNode):
    value: str

    def evaluate(self, context):
        return self.value

    def __repr__(self):
        return f"String({self.value!r})"


@dataclass
class Variable(ASTNode):
    name: str

    def evaluate(self, context):
        val = context.get_variable(self.name)
        if val is None:
            raise NameError(f"'{self.name}' is not defined")
        return val

    def __repr__(self):
        return f"Var({self.name})"


@dataclass
class UnitRef(ASTNode):
    """Reference to a unit symbol (e.g. m, kg, kN)."""
    name: str

    def evaluate(self, context):
        from . import units as units_mod
        registry = context.get_unit_registry()
        if registry is not None:
            unit = registry.lookup(self.name)
            if unit is not None:
                return units_mod.Quantity(1.0, unit)
        # Fallback: return a symbolic quantity
        return units_mod.Quantity(1.0, units_mod.Unit(self.name))

    def __repr__(self):
        return f"Unit({self.name})"


@dataclass
class BinaryOp(ASTNode):
    operator: str
    left: ASTNode
    right: ASTNode

    def children(self):
        return [self.left, self.right]

    def evaluate(self, context):
        from . import units as units_mod

        if self.operator == ":":
            # Assignment operator
            return _eval_assignment(self.left, self.right, context)

        left_val = self.left.evaluate(context)
        right_val = self.right.evaluate(context)

        return _apply_binary_op(self.operator, left_val, right_val)

    def __repr__(self):
        return f"BinaryOp({self.operator}, {self.left}, {self.right})"


@dataclass
class UnaryOp(ASTNode):
    operator: str
    operand: ASTNode

    def children(self):
        return [self.operand]

    def evaluate(self, context):
        val = self.operand.evaluate(context)
        if self.operator == "-":
            from . import units as units_mod
            if isinstance(val, units_mod.Quantity):
                return units_mod.Quantity(-val.value, val.unit)
            return -_num(val)
        return val

    def __repr__(self):
        return f"UnaryOp({self.operator}, {self.operand})"


@dataclass
class FunctionCall(ASTNode):
    name: str
    args: list[ASTNode]
    preserve: bool = False  # user-defined override marker

    def children(self):
        return list(self.args)

    def evaluate(self, context):
        from . import functions as funcs_mod

        # Check user-defined functions first
        user_func = context.get_function(self.name, len(self.args))
        if user_func is not None:
            return user_func(self.args, context)

        # Built-in functions
        return funcs_mod.call_builtin(self.name, self.args, context)

    def __repr__(self):
        return f"FuncCall({self.name}, {self.args})"


@dataclass
class Evaluation(ASTNode):
    """The = operator: evaluate an expression and display the result."""
    expression: ASTNode

    def children(self):
        return [self.expression]

    def evaluate(self, context):
        return self.expression.evaluate(context)

    def __repr__(self):
        return f"Eval({self.expression})"


@dataclass
class Bracket(ASTNode):
    """Bracket marker -- used during parsing, not in final AST."""
    symbol: str = "("

    def evaluate(self, context):
        raise RuntimeError("Bracket node should not appear in final AST")


# ---------------------------------------------------------------------------
# Postfix (RPN) to AST tree conversion
# ---------------------------------------------------------------------------

def parse_postfix(elements: list[Element], ns: str = "") -> Optional[ASTNode]:
    """Convert a list of <e> XML elements in postfix order into an AST.

    Parameters
    ----------
    elements : list of xml.etree.ElementTree.Element
        The <e> children of an <input>, <output>, <result>, or <contract> element.
    ns : str
        XML namespace prefix (e.g. "{http://smath.info/schemas/worksheet/1.0}").

    Returns
    -------
    ASTNode or None
    """
    if not elements:
        return None

    stack: list[ASTNode] = []

    for elem in elements:
        etype = elem.get("type", "")
        text = (elem.text or "").strip()

        if etype == "operand":
            style = elem.get("style", "")
            if style == "unit":
                stack.append(UnitRef(text))
            elif style == "string":
                stack.append(StringLiteral(text))
            else:
                # Try to parse as number
                node = _parse_operand(text)
                stack.append(node)

        elif etype == "operator":
            args_count = int(elem.get("args", "2"))
            if args_count == 1:
                if len(stack) < 1:
                    stack.append(Number(0))
                operand = stack.pop()
                stack.append(UnaryOp(text, operand))
            elif args_count == 2:
                if len(stack) < 2:
                    while len(stack) < 2:
                        stack.append(Number(0))
                right = stack.pop()
                left = stack.pop()
                stack.append(BinaryOp(text, left, right))
            else:
                # N-ary operator: treat as left-associative binary chain
                operands = _pop_n(stack, args_count)
                node = operands[0]
                for i in range(1, len(operands)):
                    node = BinaryOp(text, node, operands[i])
                stack.append(node)

        elif etype == "function":
            func_name = text
            args_count = int(elem.get("args", "1"))
            preserve = elem.get("preserve", "false").lower() == "true"
            func_args = _pop_n(stack, args_count)
            stack.append(FunctionCall(func_name, func_args, preserve=preserve))

        elif etype == "bracket":
            # Brackets are grouping hints for display; they don't change
            # the postfix evaluation order. We can safely ignore them.
            pass

        else:
            # Unknown element type -- treat as operand
            if text:
                stack.append(_parse_operand(text))

    if not stack:
        return None
    if len(stack) == 1:
        return stack[0]

    # Multiple items remaining -- wrap in a sequence (shouldn't happen in
    # well-formed input, but be defensive).
    return stack[-1]


def _parse_operand(text: str) -> ASTNode:
    """Parse an operand string into a Number or Variable node."""
    try:
        val = float(text)
        if val == int(val) and "." not in text and "e" not in text.lower():
            val = int(val)
        return Number(val)
    except (ValueError, TypeError):
        return Variable(text)


def _pop_n(stack: list[ASTNode], n: int) -> list[ASTNode]:
    """Pop *n* items from *stack*, returning them in their original push order."""
    if n > len(stack):
        # Pad with zero placeholders
        padding = [Number(0)] * (n - len(stack))
        items = padding + stack[:]
        stack.clear()
    else:
        items = stack[-n:]
        del stack[-n:]
    return items


# ---------------------------------------------------------------------------
# Binary operator application
# ---------------------------------------------------------------------------

_COMPARISON_OPS = {
    "=": op_module.eq,
    "<": op_module.lt,
    ">": op_module.gt,
    "≤": op_module.le,  # <=
    "≥": op_module.ge,  # >=
    "≠": op_module.ne,  # !=
    "&": lambda a, b: int(bool(a) and bool(b)),
    "|": lambda a, b: int(bool(a) or bool(b)),
}


def _apply_binary_op(operator: str, left: Any, right: Any) -> Any:
    """Apply a binary operator to two evaluated values."""
    from . import units as units_mod

    lq = isinstance(left, units_mod.Quantity)
    rq = isinstance(right, units_mod.Quantity)

    if operator == "+":
        if lq and rq:
            return left + right
        if lq:
            return units_mod.Quantity(left.value + _num(right), left.unit)
        if rq:
            return units_mod.Quantity(_num(left) + right.value, right.unit)
        try:
            import numpy as np
            if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
                return left + right
        except ImportError:
            pass
        return _num(left) + _num(right)

    if operator == "-":
        if lq and rq:
            return left - right
        if lq:
            return units_mod.Quantity(left.value - _num(right), left.unit)
        if rq:
            return units_mod.Quantity(_num(left) - right.value, right.unit)
        try:
            import numpy as np
            if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
                return left - right
        except ImportError:
            pass
        return _num(left) - _num(right)

    if operator == "*":
        if lq and rq:
            return left * right
        if lq:
            return left * right
        if rq:
            return right * left
        # Matrix multiplication for numpy arrays
        try:
            import numpy as np
            la = isinstance(left, np.ndarray)
            ra = isinstance(right, np.ndarray)
            if la and ra:
                if left.ndim == 2 and right.ndim == 2:
                    return np.dot(left, right)
                return left * right  # element-wise for 1D
            if la:
                return left * _num(right)
            if ra:
                return _num(left) * right
        except ImportError:
            pass
        return _num(left) * _num(right)

    if operator == "/":
        if lq and rq:
            try:
                return left / right
            except ZeroDivisionError:
                return math.inf
        if lq:
            try:
                return left / right
            except ZeroDivisionError:
                return math.inf
        if rq:
            if right.value == 0:
                return math.inf
            return units_mod.Quantity(_num(left) / right.value, right.unit.reciprocal())
        try:
            import numpy as np
            if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
                return left / right
        except ImportError:
            pass
        r = _num(right)
        if r == 0:
            return math.inf
        return _num(left) / r

    if operator == "^":
        if lq:
            exp = _num(right)
            try:
                return left ** exp
            except (ValueError, ZeroDivisionError, OverflowError):
                return math.inf
        # Matrix power: A^(-1) = inverse
        try:
            import numpy as np
            if isinstance(left, np.ndarray):
                exp = _num(right)
                arr = left
                if arr.dtype == object:
                    arr = np.array([[_num(v) for v in row] for row in arr], dtype=float)
                if exp == -1:
                    return np.linalg.inv(arr)
                if exp == int(exp) and exp >= 0:
                    return np.linalg.matrix_power(arr, int(exp))
        except (ImportError, np.linalg.LinAlgError):
            pass
        try:
            return _num(left) ** _num(right)
        except (ValueError, ZeroDivisionError, OverflowError):
            return math.inf

    if operator in _COMPARISON_OPS:
        lv = left.value if lq else _num(left)
        rv = right.value if rq else _num(right)
        try:
            return int(bool(_COMPARISON_OPS[operator](lv, rv)))
        except TypeError:
            return 0

    if operator == ":":
        # Assignment -- handled at BinaryOp.evaluate level
        return right

    if operator == "=":
        # Evaluation display -- just return the left side's value
        return left

    if operator == "≡":
        # Display-only definition -- no side effects
        return left

    # Fallback
    return _num(left)


def _num(val: Any) -> float:
    """Coerce a value to a number."""
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return 0.0
    # Try to extract .value from Quantity-like objects
    if hasattr(val, "value"):
        return val.value
    return 0.0


# ---------------------------------------------------------------------------
# Assignment helpers
# ---------------------------------------------------------------------------

def _eval_assignment(target: ASTNode, value_expr: ASTNode, context) -> Any:
    """Handle the := assignment operator."""

    if isinstance(target, FunctionCall):
        # Check if this is an indexed assignment: el(matrix, row, col) := value
        if target.name == "el":
            return _eval_el_assignment(target, value_expr, context)

        # Function definition: f(x) := expr
        # Do NOT evaluate value_expr -- store it as a deferred expression
        param_names = []
        for arg in target.args:
            if isinstance(arg, Variable):
                param_names.append(arg.name)
            else:
                param_names.append(str(arg))

        func_name = target.name
        context.define_function(func_name, param_names, value_expr)
        return func_name  # return the function name symbolically

    # For non-function targets, evaluate the RHS
    value = value_expr.evaluate(context)

    if isinstance(target, Variable):
        context.set_variable(target.name, value)
        return value

    # Indexed assignment or other complex target
    if isinstance(target, BinaryOp):
        # e.g. el(result, k, 2) := ...  handled as set-element
        pass

    context.set_variable(_node_name(target), value)
    return value


def _eval_el_assignment(target: FunctionCall, value_expr: ASTNode, context) -> Any:
    """Handle el(matrix, row, col) := value_expr, including range-based iteration.

    When an index argument is a range variable (numpy array / vector), SMath
    iterates the assignment over each scalar value in the range.
    """
    try:
        import numpy as np
        HAS_NUMPY = True
    except ImportError:
        HAS_NUMPY = False

    # Detect range variables in the index args (skip arg 0, the matrix itself)
    range_var = None  # (arg_index, var_name, values)
    for i, arg in enumerate(target.args):
        if i == 0:
            continue  # skip the matrix argument
        if isinstance(arg, Variable):
            val = context.get_variable(arg.name)
            if HAS_NUMPY and isinstance(val, np.ndarray) and val.size > 1:
                range_var = (i, arg.name, val.flatten())
                break

    if range_var is not None:
        # Range-based iteration: set the variable to each scalar value,
        # evaluate the RHS and assign to the corresponding element.
        _, var_name, values = range_var
        original_val = context.get_variable(var_name)
        result = None
        for k_val in values:
            context.set_variable(var_name, float(k_val))
            value = value_expr.evaluate(context)
            _eval_element_set(target, value, context)
            result = value
        # Restore the range variable
        context.set_variable(var_name, original_val)
        return result
    else:
        value = value_expr.evaluate(context)
        return _eval_element_set(target, value, context)


def _eval_element_set(target: FunctionCall, value, context) -> Any:
    """Set a single element: el(matrix, row, col) = value  or  el(vector, idx) = value.

    Auto-expands the matrix when the target position is outside current bounds.
    """
    try:
        import numpy as np
        HAS_NUMPY = True
    except ImportError:
        HAS_NUMPY = False

    args_eval = [a.evaluate(context) for a in target.args]
    matrix = args_eval[0]

    # Get the variable name so we can update in place
    matrix_name = None
    if isinstance(target.args[0], Variable):
        matrix_name = target.args[0].name

    # Determine if the value is a non-scalar (matrix, Quantity, etc.)
    # which requires object dtype for storage
    _value_is_complex = (
        (HAS_NUMPY and isinstance(value, np.ndarray))
        or isinstance(value, (list, tuple))
        or (hasattr(value, 'value') and hasattr(value, 'unit'))  # Quantity
    )
    _preferred_dtype = object if _value_is_complex else float

    # Auto-create matrix when the variable is undefined (evaluates to a string
    # or other non-container type)
    if matrix_name and not isinstance(matrix, (list, tuple)) and not (
        HAS_NUMPY and isinstance(matrix, np.ndarray)
    ):
        if len(args_eval) == 3:
            row = int(_num(args_eval[1]))
            col = int(_num(args_eval[2]))
            if HAS_NUMPY:
                if _preferred_dtype == object:
                    matrix = np.empty((row, col), dtype=object)
                    matrix[:] = 0
                else:
                    matrix = np.zeros((row, col), dtype=float)
            else:
                matrix = [[0] * col for _ in range(row)]
            args_eval[0] = matrix
        elif len(args_eval) == 2:
            idx = int(_num(args_eval[1]))
            if HAS_NUMPY:
                if _preferred_dtype == object:
                    matrix = np.empty((idx, 1), dtype=object)
                    matrix[:] = 0
                else:
                    matrix = np.zeros((idx, 1), dtype=float)
            else:
                matrix = [[0]] * idx
            args_eval[0] = matrix
        context.set_variable(matrix_name, matrix)

    # Convert float-dtype array to object-dtype if we need to store a complex value
    if _value_is_complex and HAS_NUMPY and isinstance(matrix, np.ndarray) and matrix.dtype != object:
        matrix = matrix.astype(object)
        if matrix_name:
            context.set_variable(matrix_name, matrix)

    if len(args_eval) == 3:
        row = int(_num(args_eval[1])) - 1  # 1-based to 0-based
        col = int(_num(args_eval[2])) - 1

        if HAS_NUMPY and isinstance(matrix, np.ndarray):
            # Auto-expand the matrix if the target position is out of bounds
            need_expand = False
            new_rows = matrix.shape[0]
            new_cols = matrix.shape[1] if matrix.ndim >= 2 else 1

            if row >= new_rows:
                new_rows = row + 1
                need_expand = True
            if col >= new_cols:
                new_cols = col + 1
                need_expand = True

            if need_expand:
                if matrix.dtype == object:
                    expanded = np.empty((new_rows, new_cols), dtype=object)
                    expanded[:] = 0
                else:
                    expanded = np.zeros((new_rows, new_cols), dtype=matrix.dtype)
                # Copy existing data
                old_rows = matrix.shape[0]
                old_cols = matrix.shape[1] if matrix.ndim >= 2 else 1
                if matrix.ndim == 1:
                    for r in range(old_rows):
                        expanded[r, 0] = matrix[r]
                else:
                    expanded[:old_rows, :old_cols] = matrix
                matrix = expanded

            if 0 <= row < matrix.shape[0] and 0 <= col < matrix.shape[1]:
                matrix[row, col] = value

        elif isinstance(matrix, list):
            # Expand rows
            while row >= len(matrix):
                matrix.append([0] * (col + 1))
            if isinstance(matrix[row], list):
                while col >= len(matrix[row]):
                    matrix[row].append(0)
                matrix[row][col] = value

    elif len(args_eval) == 2:
        idx = int(_num(args_eval[1])) - 1
        if HAS_NUMPY and isinstance(matrix, np.ndarray):
            # Auto-expand vector if index is out of bounds
            if matrix.ndim == 2 and matrix.shape[1] == 1 and idx >= matrix.shape[0]:
                new_size = idx + 1
                if matrix.dtype == object:
                    expanded = np.empty((new_size, 1), dtype=object)
                    expanded[:] = 0
                else:
                    expanded = np.zeros((new_size, 1), dtype=matrix.dtype)
                expanded[:matrix.shape[0], :] = matrix
                matrix = expanded
            elif matrix.ndim == 1 and idx >= len(matrix):
                if matrix.dtype == object:
                    expanded = np.empty(idx + 1, dtype=object)
                    expanded[:] = 0
                else:
                    expanded = np.zeros(idx + 1, dtype=matrix.dtype)
                expanded[:len(matrix)] = matrix
                matrix = expanded

            if matrix.ndim == 1 and 0 <= idx < len(matrix):
                matrix[idx] = value
            elif matrix.ndim == 2 and matrix.shape[1] == 1 and 0 <= idx < matrix.shape[0]:
                matrix[idx, 0] = value
        elif isinstance(matrix, list):
            while idx >= len(matrix):
                matrix.append(0)
            matrix[idx] = value

    # Update the variable in context if we know the name
    if matrix_name:
        context.set_variable(matrix_name, matrix)

    return value


def _node_name(node: ASTNode) -> str:
    """Extract a name from a node for assignment purposes."""
    if isinstance(node, Variable):
        return node.name
    if isinstance(node, FunctionCall):
        return node.name
    return repr(node)
