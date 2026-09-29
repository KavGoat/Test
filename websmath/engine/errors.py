"""SMath error messages (English), as shown in the error tip under a region.

Texts marked "observed" were read back from SMath Cloud; the others follow
the same wording style.
"""
from __future__ import annotations


class SMathError(Exception):
    """An evaluation error attached to a part of the expression."""

    def __init__(self, message: str, node=None):
        super().__init__(message)
        self.message = message
        self.node = node


MESSAGES = {
    "not_defined": "{0} - not defined.",  # observed: "y - not defined."
    "function_not_defined": "{0} - function is not defined.",  # observed: "f(#) - function is not defined."
    "units_mismatch": "Units don't match.",  # observed
    "div_zero": "Division by zero.",
    "args_count": "Incorrect number of arguments.",
    "must_be_real": "Argument must be real.",
    "must_be_dimensionless": "Argument must be dimensionless.",
    "must_be_integer": "Argument must be an integer.",
    "must_be_matrix": "Argument must be a matrix.",
    "must_be_string": "Argument must be a string.",
    "index_range": "Index was outside the bounds of the array.",
    "matrix_size": "Matrix dimensions do not match.",
    "not_square": "Matrix must be square.",
    "singular": "Matrix is singular.",
    "cannot_evaluate": "Cannot evaluate expression.",
    "missing_operand": "Fill in all empty elements.",  # observed
    "syntax": "Syntax is incorrect.",  # observed
    "units_in_exponent": "Operation cannot be performed with units.",  # observed
    "no_solution": "No solution found.",
    "iterations": "Maximum number of iterations exceeded.",
    "interrupted": "Calculation interrupted: it took too long.",
    "recursion": "Recursion is too deep.",
    "overflow": "Result is above max. allowed positive number.",  # observed: exp(1000), 10^400, 171!, cot(0)
    "log_zero": "Logarithm of zero is not defined.",  # observed: ln(0)
    "uncertainty": "Uncertainty.",  # observed: 0^0
    "factorial": "Factorial is defined for real numbers and zero.",  # observed (sic): 3.5!
    "round_range": "Coefficient of rounding should be in the range from 0 to 15 inclusive.",  # observed
    "function_units": "Operation cannot be performed with units.",  # observed: sin(1'm)
}


def err(key: str, *args, node=None) -> SMathError:
    return SMathError(MESSAGES[key].format(*args), node)
