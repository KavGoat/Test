"""Built-in math functions for SMath Studio expression evaluation."""

from __future__ import annotations

import math
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .expression import ASTNode

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore
    HAS_NUMPY = False

from .units import Quantity, Unit, DIMENSIONLESS


def _num(val: Any) -> float:
    """Coerce to float."""
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, Quantity):
        return val.value
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _ensure_list(val: Any) -> list:
    """Ensure a value is a list (for matrix/vector operations)."""
    if isinstance(val, list):
        return val
    if HAS_NUMPY and isinstance(val, np.ndarray):
        return val.tolist()
    return [val]


def _safe_scalar(val):
    """Extract a Python scalar from a numpy value, or return complex values as-is."""
    if HAS_NUMPY:
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, (np.floating,)):
            return float(val)
        if isinstance(val, np.ndarray):
            return val  # return arrays as-is (e.g. matrix stored in object array)
    if isinstance(val, (int, float)):
        return val
    return val


def _ensure_float_array(arr):
    """Convert a numpy array to float dtype if it's an object array."""
    if HAS_NUMPY and isinstance(arr, np.ndarray) and arr.dtype == object:
        try:
            return np.array([[_num(v) for v in row] for row in arr], dtype=float)
        except (TypeError, ValueError):
            return arr.astype(float)
    return arr


# ---------------------------------------------------------------------------
# Built-in function implementations
# ---------------------------------------------------------------------------

def _builtin_sin(args, ctx):
    return math.sin(_num(args[0].evaluate(ctx)))

def _builtin_cos(args, ctx):
    return math.cos(_num(args[0].evaluate(ctx)))

def _builtin_tan(args, ctx):
    return math.tan(_num(args[0].evaluate(ctx)))

def _builtin_asin(args, ctx):
    v = _num(args[0].evaluate(ctx))
    v = max(-1.0, min(1.0, v))
    return math.asin(v)

def _builtin_acos(args, ctx):
    v = _num(args[0].evaluate(ctx))
    v = max(-1.0, min(1.0, v))
    return math.acos(v)

def _builtin_atan(args, ctx):
    return math.atan(_num(args[0].evaluate(ctx)))

def _builtin_atan2(args, ctx):
    return math.atan2(_num(args[0].evaluate(ctx)), _num(args[1].evaluate(ctx)))

def _builtin_sinh(args, ctx):
    return math.sinh(_num(args[0].evaluate(ctx)))

def _builtin_cosh(args, ctx):
    return math.cosh(_num(args[0].evaluate(ctx)))

def _builtin_tanh(args, ctx):
    return math.tanh(_num(args[0].evaluate(ctx)))

def _builtin_exp(args, ctx):
    return math.exp(_num(args[0].evaluate(ctx)))

def _builtin_ln(args, ctx):
    v = _num(args[0].evaluate(ctx))
    if v <= 0:
        return -math.inf if v == 0 else math.nan
    return math.log(v)

def _builtin_log(args, ctx):
    v = _num(args[0].evaluate(ctx))
    if v <= 0:
        return -math.inf if v == 0 else math.nan
    if len(args) == 1:
        return math.log10(v)
    base = _num(args[1].evaluate(ctx))
    if base <= 0 or base == 1:
        return math.nan
    return math.log(v, base)

def _builtin_sqrt(args, ctx):
    val = args[0].evaluate(ctx)
    if isinstance(val, Quantity):
        return val ** 0.5
    v = _num(val)
    if v < 0:
        return complex(0, math.sqrt(-v))
    return math.sqrt(v)

def _builtin_abs(args, ctx):
    val = args[0].evaluate(ctx)
    if isinstance(val, Quantity):
        return Quantity(abs(val.value), val.unit)
    v = _num(val)
    return abs(v)

def _builtin_sign(args, ctx):
    val = _num(args[0].evaluate(ctx))
    if val > 0:
        return 1
    elif val < 0:
        return -1
    return 0

def _builtin_ceil(args, ctx):
    return math.ceil(_num(args[0].evaluate(ctx)))

def _builtin_floor(args, ctx):
    return math.floor(_num(args[0].evaluate(ctx)))

def _builtin_round(args, ctx):
    val = _num(args[0].evaluate(ctx))
    if len(args) > 1:
        places = int(_num(args[1].evaluate(ctx)))
        return round(val, places)
    return round(val)

def _builtin_max(args, ctx):
    if len(args) >= 2:
        vals = [_num(a.evaluate(ctx)) for a in args]
        return max(vals)
    val = args[0].evaluate(ctx)
    if isinstance(val, list):
        flat = _flatten(val)
        return max(_num(v) for v in flat)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        return float(np.max(val))
    return _num(val)

def _builtin_min(args, ctx):
    if len(args) >= 2:
        vals = [_num(a.evaluate(ctx)) for a in args]
        return min(vals)
    val = args[0].evaluate(ctx)
    if isinstance(val, list):
        flat = _flatten(val)
        return min(_num(v) for v in flat)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        return float(np.min(val))
    return _num(val)

def _builtin_mod(args, ctx):
    a = _num(args[0].evaluate(ctx))
    b = _num(args[1].evaluate(ctx))
    return a % b

def _builtin_factorial(args, ctx):
    return math.factorial(int(_num(args[0].evaluate(ctx))))

def _builtin_Gamma(args, ctx):
    return math.gamma(_num(args[0].evaluate(ctx)))

def _builtin_erf(args, ctx):
    return math.erf(_num(args[0].evaluate(ctx)))

def _builtin_cot(args, ctx):
    v = _num(args[0].evaluate(ctx))
    return math.cos(v) / math.sin(v)

def _builtin_sec(args, ctx):
    return 1.0 / math.cos(_num(args[0].evaluate(ctx)))

def _builtin_csc(args, ctx):
    return 1.0 / math.sin(_num(args[0].evaluate(ctx)))

def _builtin_acot(args, ctx):
    return math.atan(1.0 / _num(args[0].evaluate(ctx)))

def _builtin_asec(args, ctx):
    return math.acos(1.0 / _num(args[0].evaluate(ctx)))

def _builtin_acsc(args, ctx):
    return math.asin(1.0 / _num(args[0].evaluate(ctx)))

def _builtin_asinh(args, ctx):
    return math.asinh(_num(args[0].evaluate(ctx)))

def _builtin_acosh(args, ctx):
    return math.acosh(_num(args[0].evaluate(ctx)))

def _builtin_atanh(args, ctx):
    return math.atanh(_num(args[0].evaluate(ctx)))

def _builtin_coth(args, ctx):
    v = _num(args[0].evaluate(ctx))
    return math.cosh(v) / math.sinh(v)

def _builtin_sech(args, ctx):
    return 1.0 / math.cosh(_num(args[0].evaluate(ctx)))

def _builtin_csch(args, ctx):
    return 1.0 / math.sinh(_num(args[0].evaluate(ctx)))

def _builtin_log2(args, ctx):
    return math.log2(_num(args[0].evaluate(ctx)))

def _builtin_cbrt(args, ctx):
    v = _num(args[0].evaluate(ctx))
    return math.copysign(abs(v) ** (1.0/3.0), v)

def _builtin_nthroot(args, ctx):
    val = _num(args[0].evaluate(ctx))
    n = _num(args[1].evaluate(ctx))
    if n == 0:
        return math.inf
    return math.copysign(abs(val) ** (1.0/n), val) if val < 0 and n % 2 == 1 else val ** (1.0/n)

def _builtin_Re(args, ctx):
    val = args[0].evaluate(ctx)
    if isinstance(val, complex):
        return val.real
    return _num(val)

def _builtin_Im(args, ctx):
    val = args[0].evaluate(ctx)
    if isinstance(val, complex):
        return val.imag
    return 0.0

def _builtin_arg(args, ctx):
    val = args[0].evaluate(ctx)
    if isinstance(val, complex):
        import cmath
        return cmath.phase(val)
    v = _num(val)
    return 0.0 if v >= 0 else math.pi

def _builtin_conj(args, ctx):
    val = args[0].evaluate(ctx)
    if isinstance(val, complex):
        return val.conjugate()
    return _num(val)

def _builtin_gcd(args, ctx):
    a = int(_num(args[0].evaluate(ctx)))
    b = int(_num(args[1].evaluate(ctx)))
    return math.gcd(a, b)

def _builtin_lcm(args, ctx):
    a = int(_num(args[0].evaluate(ctx)))
    b = int(_num(args[1].evaluate(ctx)))
    return abs(a * b) // math.gcd(a, b) if a and b else 0

def _builtin_isPrime(args, ctx):
    n = int(_num(args[0].evaluate(ctx)))
    if n < 2:
        return 0
    if n < 4:
        return 1
    if n % 2 == 0 or n % 3 == 0:
        return 0
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return 0
        i += 6
    return 1

def _builtin_Cn(args, ctx):
    n = int(_num(args[0].evaluate(ctx)))
    k = int(_num(args[1].evaluate(ctx)))
    return math.comb(n, k)

def _builtin_Pn(args, ctx):
    n = int(_num(args[0].evaluate(ctx)))
    k = int(_num(args[1].evaluate(ctx)))
    return math.perm(n, k)

def _builtin_length(args, ctx):
    val = args[0].evaluate(ctx)
    if isinstance(val, str):
        return len(val)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        return max(val.shape)
    if isinstance(val, list):
        return len(val)
    return 1

def _builtin_submatrix(args, ctx):
    matrix = args[0].evaluate(ctx)
    r1 = int(_num(args[1].evaluate(ctx))) - 1
    c1 = int(_num(args[2].evaluate(ctx))) - 1
    r2 = int(_num(args[3].evaluate(ctx)))
    c2 = int(_num(args[4].evaluate(ctx)))
    if HAS_NUMPY and isinstance(matrix, np.ndarray):
        return matrix[r1:r2, c1:c2]
    return matrix

def _builtin_eigenvals(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        arr = _ensure_float_array(val)
        eigenvalues = np.linalg.eigvals(arr)
        if np.all(np.isreal(eigenvalues)):
            eigenvalues = np.real(eigenvalues)
        return eigenvalues.reshape(-1, 1)
    return val

def _builtin_eigenvecs(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        arr = _ensure_float_array(val)
        _, vecs = np.linalg.eig(arr)
        return vecs
    return val

def _builtin_rank(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        arr = _ensure_float_array(val)
        return int(np.linalg.matrix_rank(arr))
    return 1

def _builtin_norm(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        arr = _ensure_float_array(val)
        return float(np.linalg.norm(arr))
    return abs(_num(val))

def _builtin_cross(args, ctx):
    a = args[0].evaluate(ctx)
    b = args[1].evaluate(ctx)
    if HAS_NUMPY:
        a_arr = np.array(_flatten(a), dtype=float) if not isinstance(a, np.ndarray) else a.flatten()
        b_arr = np.array(_flatten(b), dtype=float) if not isinstance(b, np.ndarray) else b.flatten()
        return np.cross(a_arr, b_arr).reshape(-1, 1)
    return 0

def _builtin_dot(args, ctx):
    a = args[0].evaluate(ctx)
    b = args[1].evaluate(ctx)
    if HAS_NUMPY:
        a_arr = np.array(_flatten(a), dtype=float) if not isinstance(a, np.ndarray) else a.flatten()
        b_arr = np.array(_flatten(b), dtype=float) if not isinstance(b, np.ndarray) else b.flatten()
        return float(np.dot(a_arr, b_arr))
    return 0

def _builtin_zeros(args, ctx):
    rows = int(_num(args[0].evaluate(ctx)))
    cols = int(_num(args[1].evaluate(ctx))) if len(args) > 1 else 1
    if HAS_NUMPY:
        return np.zeros((rows, cols))
    return [[0] * cols for _ in range(rows)]

def _builtin_ones(args, ctx):
    rows = int(_num(args[0].evaluate(ctx)))
    cols = int(_num(args[1].evaluate(ctx))) if len(args) > 1 else 1
    if HAS_NUMPY:
        return np.ones((rows, cols))
    return [[1] * cols for _ in range(rows)]

def _builtin_diag(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY:
        if isinstance(val, np.ndarray):
            return np.diag(val.flatten() if val.ndim > 1 else val)
        return np.diag([_num(val)])
    return val

def _builtin_solve(args, ctx):
    A = args[0].evaluate(ctx)
    b = args[1].evaluate(ctx)
    if HAS_NUMPY:
        A_arr = _ensure_float_array(np.array(A) if not isinstance(A, np.ndarray) else A)
        b_arr = _ensure_float_array(np.array(b) if not isinstance(b, np.ndarray) else b)
        return np.linalg.solve(A_arr, b_arr)
    return 0

def _builtin_lsolve(args, ctx):
    return _builtin_solve(args, ctx)

def _builtin_variance(args, ctx):
    val = args[0].evaluate(ctx)
    flat = _flatten_numeric(val)
    n = len(flat)
    if n < 2:
        return 0
    m = sum(flat) / n
    return sum((x - m) ** 2 for x in flat) / (n - 1)

def _builtin_sort(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        return np.sort(val, axis=0)
    if isinstance(val, list):
        return sorted(val, key=lambda x: _num(x) if not isinstance(x, list) else _num(x[0]))
    return val

def _builtin_reverse(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        return val[::-1]
    if isinstance(val, list):
        return list(reversed(val))
    return val

def _builtin_unique(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        return np.unique(val).reshape(-1, 1)
    return val

def _builtin_str2num(args, ctx):
    val = args[0].evaluate(ctx)
    try:
        return float(str(val))
    except ValueError:
        return 0.0

def _builtin_strlen(args, ctx):
    val = args[0].evaluate(ctx)
    return len(str(val))

def _builtin_substr(args, ctx):
    s = str(args[0].evaluate(ctx))
    start = int(_num(args[1].evaluate(ctx)))
    if len(args) > 2:
        length = int(_num(args[2].evaluate(ctx)))
        return s[start:start + length]
    return s[start:]

def _builtin_strpos(args, ctx):
    s = str(args[0].evaluate(ctx))
    sub = str(args[1].evaluate(ctx))
    pos = s.find(sub)
    return pos

def _builtin_strsplit(args, ctx):
    s = str(args[0].evaluate(ctx))
    delim = str(args[1].evaluate(ctx)) if len(args) > 1 else " "
    parts = s.split(delim)
    if HAS_NUMPY:
        return np.array(parts, dtype=object).reshape(-1, 1)
    return [[p] for p in parts]

def _builtin_upper(args, ctx):
    return str(args[0].evaluate(ctx)).upper()

def _builtin_lower(args, ctx):
    return str(args[0].evaluate(ctx)).lower()

def _builtin_numericValue(args, ctx):
    val = args[0].evaluate(ctx)
    if isinstance(val, Quantity):
        return val.value
    return _num(val)


# ---------------------------------------------------------------------------
# Matrix functions
# ---------------------------------------------------------------------------

def _builtin_mat(args, ctx):
    """Create a matrix. Last two args are rows and cols, preceding args are elements
    laid out row-major."""
    evaluated = [a.evaluate(ctx) for a in args]
    if len(evaluated) < 3:
        return evaluated

    cols = int(_num(evaluated[-1]))
    rows = int(_num(evaluated[-2]))
    elements = evaluated[:-2]

    # Build matrix as list of lists
    matrix = []
    idx = 0
    for r in range(rows):
        row = []
        for c in range(cols):
            if idx < len(elements):
                row.append(elements[idx])
            else:
                row.append(0)
            idx += 1
        matrix.append(row)

    if HAS_NUMPY:
        # Only convert to numpy if all elements are numeric (no strings, no Quantities)
        all_numeric = all(
            isinstance(v, (int, float, np.integer, np.floating))
            for row in matrix for v in row
        )
        if all_numeric:
            try:
                return np.array([[_num(v) for v in row] for row in matrix], dtype=float)
            except (TypeError, ValueError):
                pass
        # For mixed-type matrices, use object dtype
        try:
            return np.array(matrix, dtype=object)
        except Exception:
            pass

    return matrix


def _builtin_el(args, ctx):
    """Element access: el(matrix, row, col) or el(vector, index)."""
    evaluated = [a.evaluate(ctx) for a in args]
    matrix = evaluated[0]

    if len(evaluated) == 2:
        # Vector element access (1-based)
        idx = int(_num(evaluated[1])) - 1
        if HAS_NUMPY and isinstance(matrix, np.ndarray):
            if matrix.ndim == 1:
                if 0 <= idx < len(matrix):
                    return _safe_scalar(matrix[idx])
                return 0
            elif matrix.ndim == 2:
                if matrix.shape[1] == 1:
                    # Column vector
                    if 0 <= idx < matrix.shape[0]:
                        return _safe_scalar(matrix[idx, 0])
                elif matrix.shape[0] == 1:
                    # Row vector
                    if 0 <= idx < matrix.shape[1]:
                        return _safe_scalar(matrix[0, idx])
                else:
                    # General matrix -- return row as 1D
                    if 0 <= idx < matrix.shape[0]:
                        row = matrix[idx]
                        if row.shape[0] == 1:
                            return _safe_scalar(row[0])
                        return row
                return 0
        if isinstance(matrix, list):
            if 0 <= idx < len(matrix):
                val = matrix[idx]
                # Unwrap single-element lists
                if isinstance(val, list) and len(val) == 1:
                    return val[0]
                return val
        return 0

    if len(evaluated) >= 3:
        row = int(_num(evaluated[1])) - 1
        col = int(_num(evaluated[2])) - 1
        if HAS_NUMPY and isinstance(matrix, np.ndarray):
            if matrix.ndim == 2 and 0 <= row < matrix.shape[0] and 0 <= col < matrix.shape[1]:
                val = matrix[row, col]
                # For object-dtype arrays or non-numeric values, return as-is
                if isinstance(val, (int, float)):
                    return val
                if isinstance(val, (np.integer, np.floating)):
                    return float(val)
                return val
            elif matrix.ndim == 1 and row == 0 and 0 <= col < len(matrix):
                val = matrix[col]
                if isinstance(val, (np.integer, np.floating)):
                    return float(val)
                return val
        elif isinstance(matrix, list):
            if 0 <= row < len(matrix) and isinstance(matrix[row], list):
                if 0 <= col < len(matrix[row]):
                    return matrix[row][col]
        return 0

    return matrix


def _builtin_rows(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        return val.shape[0]
    if isinstance(val, list):
        return len(val)
    return 1


def _builtin_cols(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        return val.shape[1] if val.ndim >= 2 else 1
    if isinstance(val, list) and val and isinstance(val[0], list):
        return len(val[0])
    return 1


def _builtin_col(args, ctx):
    """Extract a column from a matrix."""
    matrix = args[0].evaluate(ctx)
    col_idx = int(_num(args[1].evaluate(ctx))) - 1

    if HAS_NUMPY and isinstance(matrix, np.ndarray):
        return matrix[:, col_idx:col_idx+1]
    if isinstance(matrix, list):
        return [[row[col_idx]] for row in matrix if isinstance(row, list) and col_idx < len(row)]
    return matrix


def _builtin_det(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        arr = _ensure_float_array(val)
        return float(np.linalg.det(arr))
    return 0


def _builtin_invert(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        arr = _ensure_float_array(val)
        return np.linalg.inv(arr)
    return val


def _builtin_transpose(args, ctx):
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        return val.T
    if isinstance(val, list) and val and isinstance(val[0], list):
        rows = len(val)
        cols = len(val[0])
        return [[val[r][c] for r in range(rows)] for c in range(cols)]
    return val


def _builtin_identity(args, ctx):
    n = int(_num(args[0].evaluate(ctx)))
    if HAS_NUMPY:
        return np.eye(n)
    return [[1 if i == j else 0 for j in range(n)] for i in range(n)]


def _builtin_stack(args, ctx):
    """Stack matrices vertically."""
    evaluated = [a.evaluate(ctx) for a in args]
    if HAS_NUMPY:
        arrays = []
        for v in evaluated:
            if isinstance(v, np.ndarray):
                arrays.append(v)
            elif isinstance(v, list):
                arrays.append(np.array(v))
            else:
                arrays.append(np.array([[_num(v)]]))
        try:
            return np.vstack(arrays)
        except Exception:
            return evaluated
    return evaluated


def _builtin_augment(args, ctx):
    """Augment (horizontally concatenate) matrices."""
    evaluated = [a.evaluate(ctx) for a in args]
    if HAS_NUMPY:
        arrays = [np.atleast_2d(np.array(v) if isinstance(v, list) else np.array([[_num(v)]])) for v in evaluated]
        try:
            return np.hstack(arrays)
        except Exception:
            return evaluated
    return evaluated


def _builtin_tr(args, ctx):
    """Matrix trace -- sum of diagonal elements."""
    val = args[0].evaluate(ctx)
    if HAS_NUMPY and isinstance(val, np.ndarray):
        if val.ndim == 2:
            return float(np.trace(val))
        return float(val[0]) if val.size > 0 else 0
    if isinstance(val, list) and val and isinstance(val[0], list):
        return sum(_num(val[i][i]) for i in range(min(len(val), len(val[0]))))
    return _num(val)


def _builtin_polyroots(args, ctx):
    """Find roots of a polynomial given its coefficients vector.
    Coefficients are ordered from highest degree to lowest (or ascending --
    SMath uses ascending order with p[1] = constant term)."""
    coeffs = args[0].evaluate(ctx)
    if HAS_NUMPY:
        if isinstance(coeffs, np.ndarray):
            flat = coeffs.flatten()
        elif isinstance(coeffs, list):
            flat = np.array(_flatten(coeffs), dtype=float)
        else:
            return coeffs

        # SMath stores polynomial coefficients in ascending order (constant first)
        # numpy.roots expects descending order (highest degree first)
        coeffs_desc = flat[::-1]

        # Remove leading zeros
        while len(coeffs_desc) > 1 and coeffs_desc[0] == 0:
            coeffs_desc = coeffs_desc[1:]

        roots = np.roots(coeffs_desc)
        # Return real parts if all roots are real
        if np.all(np.isreal(roots)):
            roots = np.real(roots)
        return roots.reshape(-1, 1)
    return coeffs


def _builtin_csort(args, ctx):
    """Sort matrix by column."""
    matrix = args[0].evaluate(ctx)
    col_idx = int(_num(args[1].evaluate(ctx))) - 1
    if HAS_NUMPY and isinstance(matrix, np.ndarray):
        if matrix.ndim < 2 or col_idx >= matrix.shape[1]:
            return matrix
        col_data = matrix[:, col_idx]
        # Extract numeric sort keys from potentially mixed-type columns
        try:
            sort_keys = np.array([_num(v) for v in col_data], dtype=float)
            indices = np.argsort(sort_keys)
            return matrix[indices]
        except (TypeError, ValueError):
            return matrix
    return matrix


# ---------------------------------------------------------------------------
# Statistical functions
# ---------------------------------------------------------------------------

def _builtin_mean(args, ctx):
    val = args[0].evaluate(ctx)
    flat = _flatten_numeric(val)
    return sum(flat) / len(flat) if flat else 0

def _builtin_median(args, ctx):
    val = args[0].evaluate(ctx)
    flat = sorted(_flatten_numeric(val))
    n = len(flat)
    if n == 0:
        return 0
    mid = n // 2
    if n % 2 == 0:
        return (flat[mid - 1] + flat[mid]) / 2
    return flat[mid]

def _builtin_stdev(args, ctx):
    val = args[0].evaluate(ctx)
    flat = _flatten_numeric(val)
    n = len(flat)
    if n < 2:
        return 0
    m = sum(flat) / n
    return math.sqrt(sum((x - m) ** 2 for x in flat) / (n - 1))


# ---------------------------------------------------------------------------
# Control flow
# ---------------------------------------------------------------------------

def _builtin_if(args, ctx):
    """if(condition, true_value, false_value)"""
    cond = args[0].evaluate(ctx)
    if _num(cond):
        return args[1].evaluate(ctx)
    if len(args) > 2:
        return args[2].evaluate(ctx)
    return 0


def _builtin_for(args, ctx):
    """Two forms:
    4 args: for(var:=start, condition, var:=var+step, body)
    3 args: for(var, iterable, body) -- iterate var over a range/vector
    """
    if len(args) == 3:
        # for(var, iterable, body) -- range-based iteration
        from .expression import Variable
        var = args[0]
        if isinstance(var, Variable):
            var_name = var.name
        else:
            var_name = str(var.evaluate(ctx))

        iterable = args[1].evaluate(ctx)
        body = args[2]

        result = 0
        if HAS_NUMPY and isinstance(iterable, np.ndarray):
            for val in iterable.flatten():
                ctx.set_variable(var_name, float(val))
                result = body.evaluate(ctx)
        elif isinstance(iterable, list):
            flat = _flatten(iterable)
            for val in flat:
                ctx.set_variable(var_name, _num(val))
                result = body.evaluate(ctx)
        else:
            ctx.set_variable(var_name, iterable)
            result = body.evaluate(ctx)

        return result

    # 4-arg form: for(init, condition, increment, body)
    args[0].evaluate(ctx)

    result = 0
    max_iter = 100000
    i = 0
    while i < max_iter:
        cond = args[1].evaluate(ctx)
        if not _num(cond):
            break
        result = args[3].evaluate(ctx)
        args[2].evaluate(ctx)  # increment
        i += 1

    return result


def _builtin_while(args, ctx):
    """while(condition, body)"""
    cond_expr = args[0]
    body_expr = args[1]

    result = 0
    max_iter = 100000
    i = 0
    while i < max_iter:
        cond = cond_expr.evaluate(ctx)
        if not _num(cond):
            break
        result = body_expr.evaluate(ctx)
        i += 1

    return result


def _builtin_line(args, ctx):
    """line(expr1, expr2, ..., count, 1) -- execute a block of lines.
    The last arg is usually 1, the second-to-last is the number of expressions."""
    # Evaluate all but the last two args (which are count and flag)
    result = 0
    n = len(args)
    if n >= 3:
        count = int(_num(args[-2].evaluate(ctx)))
        for i in range(min(count, n - 2)):
            result = args[i].evaluate(ctx)
    else:
        for a in args:
            result = a.evaluate(ctx)
    return result


def _builtin_range(args, ctx):
    """range(start, end) -- create a vector of integers from start to end.
    range(start, end, intervals) -- create intervals+1 evenly spaced values."""
    start_val = _num(args[0].evaluate(ctx))
    end_val = _num(args[1].evaluate(ctx))

    if len(args) >= 3:
        # range(start, end, intervals): intervals+1 evenly spaced values
        intervals = int(_num(args[2].evaluate(ctx)))
        if intervals <= 0:
            intervals = 1
        step = (end_val - start_val) / intervals
        values = [start_val + i * step for i in range(intervals + 1)]
    else:
        # range(start, end): integers from start to end inclusive
        start = int(start_val)
        end = int(end_val)
        step = 1 if end >= start else -1
        values = list(range(start, end + step, step))

    if HAS_NUMPY:
        return np.array(values, dtype=float).reshape(-1, 1)
    return [[v] for v in values]


def _builtin_eval(args, ctx):
    """Evaluate an expression numerically."""
    return args[0].evaluate(ctx)


def _builtin_diff(args, ctx):
    """Numerical differentiation: diff(expr, var)
    Uses central difference with small h."""
    # For symbolic differentiation we'd need a CAS;
    # here we do numerical differentiation
    expr = args[0]
    var = args[1]

    from .expression import Variable
    if isinstance(var, Variable):
        var_name = var.name
    else:
        var_name = str(var.evaluate(ctx))

    h = 1e-8
    original = ctx.get_variable(var_name)
    x0 = _num(original) if original is not None else 0

    ctx.set_variable(var_name, x0 + h)
    f_plus = _num(expr.evaluate(ctx))

    ctx.set_variable(var_name, x0 - h)
    f_minus = _num(expr.evaluate(ctx))

    ctx.set_variable(var_name, original if original is not None else x0)

    return (f_plus - f_minus) / (2 * h)


def _builtin_nintegrate(args, ctx):
    """Numerical integration using Simpson's rule.

    4 args: int(f(x), x, a, b) -- definite integral
    2 args: int(f(x), x) -- symbolic (not supported, returns 0)
    """
    if len(args) < 4:
        # Indefinite integral / symbolic -- not supported without CAS
        return 0

    func_expr = args[0]
    from .expression import Variable
    var = args[1]
    if isinstance(var, Variable):
        var_name = var.name
    else:
        var_name = str(var.evaluate(ctx))

    a = _num(args[2].evaluate(ctx))
    b = _num(args[3].evaluate(ctx))

    n = 100  # number of intervals
    if a == b:
        return 0.0
    h = (b - a) / n
    total = 0.0

    for i in range(n + 1):
        x = a + i * h
        ctx.set_variable(var_name, x)
        fx = _num(func_expr.evaluate(ctx))
        if i == 0 or i == n:
            total += fx
        elif i % 2 == 1:
            total += 4 * fx
        else:
            total += 2 * fx

    return total * h / 3


def _builtin_sum(args, ctx):
    """sum(expr, var, start, end) or sum(vector)."""
    if len(args) == 1:
        val = args[0].evaluate(ctx)
        flat = _flatten_numeric(val)
        return sum(flat)

    if len(args) >= 4:
        expr = args[0]
        from .expression import Variable
        var = args[1]
        if isinstance(var, Variable):
            var_name = var.name
        else:
            var_name = str(var.evaluate(ctx))

        start = int(_num(args[2].evaluate(ctx)))
        end = int(_num(args[3].evaluate(ctx)))

        total = None
        for i in range(start, end + 1):
            ctx.set_variable(var_name, i)
            val = expr.evaluate(ctx)
            if total is None:
                total = val
            else:
                total = total + val

        return total if total is not None else 0

    return 0


def _builtin_product(args, ctx):
    """product(expr, var, start, end)."""
    if len(args) >= 4:
        expr = args[0]
        from .expression import Variable
        var = args[1]
        if isinstance(var, Variable):
            var_name = var.name
        else:
            var_name = str(var.evaluate(ctx))

        start = int(_num(args[2].evaluate(ctx)))
        end = int(_num(args[3].evaluate(ctx)))

        total = None
        for i in range(start, end + 1):
            ctx.set_variable(var_name, i)
            val = expr.evaluate(ctx)
            if total is None:
                total = val
            else:
                # Handle matrix and scalar multiplication correctly
                t_arr = HAS_NUMPY and isinstance(total, np.ndarray)
                v_arr = HAS_NUMPY and isinstance(val, np.ndarray)
                if t_arr and v_arr:
                    if total.ndim == 2 and val.ndim == 2:
                        total = np.dot(total, val)
                    else:
                        total = total * val
                elif t_arr:
                    total = total * _num(val)  # scalar * matrix
                elif v_arr:
                    total = _num(total) * val  # scalar * matrix
                else:
                    total = _num(total) * _num(val)
        return total if total is not None else 1.0
    return 0


# Conversion functions
def _builtin_num2str(args, ctx):
    val = args[0].evaluate(ctx)
    return str(_num(val))


def _builtin_concat(args, ctx):
    parts = [str(a.evaluate(ctx)) for a in args]
    return "".join(parts)


# System functions
def _builtin_sys(args, ctx):
    """System plot function -- returns the argument list for plot assembly."""
    return [a.evaluate(ctx) for a in args]


def _builtin_row(args, ctx):
    """Extract a row from a matrix. row(M, i) returns the i-th row (1-based)."""
    matrix = args[0].evaluate(ctx)
    row_idx = int(_num(args[1].evaluate(ctx))) - 1

    if HAS_NUMPY and isinstance(matrix, np.ndarray):
        return matrix[row_idx:row_idx+1, :]
    if isinstance(matrix, list) and row_idx < len(matrix):
        row = matrix[row_idx]
        if isinstance(row, list):
            return [row]
        return [[row]]
    return matrix


def _builtin_lim(args, ctx):
    """Numeric limit approximation. lim(expr, var, value).
    Evaluates the expression at values approaching the limit point."""
    if len(args) < 3:
        return args[0].evaluate(ctx)

    from .expression import Variable
    expr = args[0]
    var_node = args[1]
    target = _num(args[2].evaluate(ctx))

    var_name = var_node.name if isinstance(var_node, Variable) else str(var_node.evaluate(ctx))
    old_val = ctx.get_variable(var_name)

    try:
        deltas = [1e-2, 1e-4, 1e-6, 1e-8, 1e-10]
        results = []
        for d in deltas:
            ctx.set_variable(var_name, target + d)
            v1 = _num(expr.evaluate(ctx))
            ctx.set_variable(var_name, target - d)
            v2 = _num(expr.evaluate(ctx))
            results.append((v1 + v2) / 2)
        return results[-1]
    finally:
        if old_val is not None:
            ctx.set_variable(var_name, old_val)
        else:
            ctx.set_variable(var_name, None)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BUILTIN_FUNCTIONS: dict[str, Callable] = {
    # Trig
    "sin": _builtin_sin,
    "cos": _builtin_cos,
    "tan": _builtin_tan,
    "cot": _builtin_cot,
    "sec": _builtin_sec,
    "csc": _builtin_csc,
    "asin": _builtin_asin,
    "acos": _builtin_acos,
    "atan": _builtin_atan,
    "acot": _builtin_acot,
    "asec": _builtin_asec,
    "acsc": _builtin_acsc,
    "atan2": _builtin_atan2,
    # Hyperbolic
    "sinh": _builtin_sinh,
    "cosh": _builtin_cosh,
    "tanh": _builtin_tanh,
    "coth": _builtin_coth,
    "sech": _builtin_sech,
    "csch": _builtin_csch,
    "asinh": _builtin_asinh,
    "acosh": _builtin_acosh,
    "atanh": _builtin_atanh,
    # Exponential / log
    "exp": _builtin_exp,
    "ln": _builtin_ln,
    "log": _builtin_log,
    "log2": _builtin_log2,
    "sqrt": _builtin_sqrt,
    "cbrt": _builtin_cbrt,
    "nthroot": _builtin_nthroot,
    # Basic math
    "abs": _builtin_abs,
    "sign": _builtin_sign,
    "ceil": _builtin_ceil,
    "floor": _builtin_floor,
    "round": _builtin_round,
    "max": _builtin_max,
    "min": _builtin_min,
    "mod": _builtin_mod,
    "factorial": _builtin_factorial,
    "numericValue": _builtin_numericValue,
    # Complex numbers
    "Re": _builtin_Re,
    "Im": _builtin_Im,
    "arg": _builtin_arg,
    "conj": _builtin_conj,
    # Number theory
    "gcd": _builtin_gcd,
    "lcm": _builtin_lcm,
    "isPrime": _builtin_isPrime,
    "Cn": _builtin_Cn,
    "Pn": _builtin_Pn,
    # Special
    "Gamma": _builtin_Gamma,
    "erf": _builtin_erf,
    # Matrix
    "mat": _builtin_mat,
    "el": _builtin_el,
    "rows": _builtin_rows,
    "cols": _builtin_cols,
    "col": _builtin_col,
    "det": _builtin_det,
    "invert": _builtin_invert,
    "transpose": _builtin_transpose,
    "identity": _builtin_identity,
    "stack": _builtin_stack,
    "augment": _builtin_augment,
    "csort": _builtin_csort,
    "tr": _builtin_tr,
    "polyroots": _builtin_polyroots,
    "submatrix": _builtin_submatrix,
    "eigenvals": _builtin_eigenvals,
    "eigenvecs": _builtin_eigenvecs,
    "rank": _builtin_rank,
    "norm": _builtin_norm,
    "cross": _builtin_cross,
    "dot": _builtin_dot,
    "zeros": _builtin_zeros,
    "ones": _builtin_ones,
    "diag": _builtin_diag,
    "solve": _builtin_solve,
    "lsolve": _builtin_lsolve,
    "length": _builtin_length,
    "sort": _builtin_sort,
    "reverse": _builtin_reverse,
    "unique": _builtin_unique,
    # Statistics
    "mean": _builtin_mean,
    "median": _builtin_median,
    "stdev": _builtin_stdev,
    "variance": _builtin_variance,
    # Control flow
    "if": _builtin_if,
    "for": _builtin_for,
    "while": _builtin_while,
    "line": _builtin_line,
    # Numeric
    "range": _builtin_range,
    "eval": _builtin_eval,
    "diff": _builtin_diff,
    "int": _builtin_nintegrate,
    "nintegrate": _builtin_nintegrate,
    # Summation / product
    "sum": _builtin_sum,
    "product": _builtin_product,
    # Conversion / string
    "num2str": _builtin_num2str,
    "str2num": _builtin_str2num,
    "concat": _builtin_concat,
    "strlen": _builtin_strlen,
    "substr": _builtin_substr,
    "strpos": _builtin_strpos,
    "strsplit": _builtin_strsplit,
    "upper": _builtin_upper,
    "lower": _builtin_lower,
    # System
    "sys": _builtin_sys,
    # European/Russian aliases used in SMath .sm files
    "tg": _builtin_tan,
    "ctg": _builtin_cot,
    "cosec": _builtin_csc,
    "arcsin": _builtin_asin,
    "arccos": _builtin_acos,
    "arctg": _builtin_atan,
    "arcctg": _builtin_acot,
    "arcsec": _builtin_asec,
    "arccosec": _builtin_acsc,
    "sh": _builtin_sinh,
    "ch": _builtin_cosh,
    "th": _builtin_tanh,
    "cth": _builtin_coth,
    "lg": _builtin_log,
    "row": _builtin_row,
    "lim": _builtin_lim,
}


def call_builtin(name: str, args: list, context) -> Any:
    """Call a built-in function by name."""
    func = BUILTIN_FUNCTIONS.get(name)
    if func is not None:
        try:
            return func(args, context)
        except (IndexError, ValueError, TypeError, ZeroDivisionError, OverflowError):
            # Gracefully handle evaluation errors in builtins
            return 0

    # Unknown function -- try to evaluate args and return something useful
    try:
        evaluated = [a.evaluate(context) for a in args]
        if len(evaluated) == 1:
            return evaluated[0]
        return evaluated
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten(val: Any) -> list:
    """Flatten nested lists / numpy arrays."""
    if HAS_NUMPY and isinstance(val, np.ndarray):
        return val.flatten().tolist()
    if isinstance(val, list):
        result = []
        for item in val:
            result.extend(_flatten(item))
        return result
    return [val]


def _flatten_numeric(val: Any) -> list[float]:
    """Flatten and convert to numeric."""
    flat = _flatten(val)
    return [_num(v) for v in flat]
