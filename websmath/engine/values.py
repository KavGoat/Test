"""Runtime values: scalars with units, matrices, strings."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .errors import err
from .units import NODIM, Quantity, dims_add, dims_scale, dims_sub


@dataclass
class Matrix:
    nrows: int
    ncols: int
    items: list = field(default_factory=list)  # row-major Values

    def get(self, i: int, j: int):
        return self.items[i * self.ncols + j]

    def copy(self) -> "Matrix":
        return Matrix(self.nrows, self.ncols, list(self.items))

    @staticmethod
    def column(values) -> "Matrix":
        values = list(values)
        return Matrix(len(values), 1, values)


@dataclass(frozen=True)
class String:
    text: str


def Q(v, dims=NODIM) -> Quantity:
    if isinstance(v, bool):
        v = 1.0 if v else 0.0
    if isinstance(v, int):
        v = float(v)
    if isinstance(v, complex) and v.imag == 0:
        v = v.real
    return Quantity(v, tuple(dims))


ONE = Q(1.0)
ZERO = Q(0.0)


def truth(v) -> bool:
    if isinstance(v, Quantity):
        return v.value != 0
    raise err("must_be_real")


def need_scalar(v, node=None) -> Quantity:
    if isinstance(v, Quantity):
        return v
    if isinstance(v, Matrix) and v.nrows == v.ncols == 1:
        return v.items[0]
    raise err("cannot_evaluate", node=node)


def need_real(v, node=None) -> float:
    q = need_scalar(v, node)
    if isinstance(q.value, complex):
        raise err("must_be_real", node=node)
    return q.value


def need_dimless(v, node=None) -> Quantity:
    q = need_scalar(v, node)
    if not q.dimensionless:
        raise err("must_be_dimensionless", node=node)
    return q


def need_int(v, node=None) -> int:
    x = need_real(need_dimless(v, node), node)
    if abs(x - round(x)) > 1e-12:
        raise err("must_be_integer", node=node)
    return int(round(x))


# ---------------------------------------------------------------------------
# arithmetic
# ---------------------------------------------------------------------------

def _elementwise(a, b, f):
    if isinstance(a, Matrix) and isinstance(b, Matrix):
        if (a.nrows, a.ncols) != (b.nrows, b.ncols):
            raise err("matrix_size")
        return Matrix(a.nrows, a.ncols, [f(x, y) for x, y in zip(a.items, b.items)])
    if isinstance(a, Matrix):
        return Matrix(a.nrows, a.ncols, [f(x, b) for x in a.items])
    if isinstance(b, Matrix):
        return Matrix(b.nrows, b.ncols, [f(a, y) for y in b.items])
    return f(a, b)


def add(a, b, sign=1):
    if isinstance(a, String) or isinstance(b, String):
        raise err("cannot_evaluate")
    if isinstance(a, Matrix) != isinstance(b, Matrix):
        raise err("matrix_size")

    def f(x, y):
        if x.dims != y.dims:
            raise err("units_mismatch")
        return Q(x.value + sign * y.value, x.dims)

    return _elementwise(a, b, f)


def sub(a, b):
    return add(a, b, -1)


def neg(a):
    if isinstance(a, Matrix):
        return Matrix(a.nrows, a.ncols, [neg(x) for x in a.items])
    a = need_scalar(a)
    return Q(-a.value, a.dims)


def _smul(x, y):
    return Q(x.value * y.value, dims_add(x.dims, y.dims))


def mul(a, b):
    if isinstance(a, String) or isinstance(b, String):
        raise err("cannot_evaluate")
    if isinstance(a, Matrix) and isinstance(b, Matrix):
        # vector · vector of equal shape (columns) -> scalar product
        if a.ncols == 1 and b.ncols == 1 and a.nrows == b.nrows and a.nrows > 1:
            acc = None
            for x, y in zip(a.items, b.items):
                p = _smul(x, y)
                acc = p if acc is None else add(acc, p)
            return acc
        if a.ncols != b.nrows:
            raise err("matrix_size")
        out = []
        for i in range(a.nrows):
            for j in range(b.ncols):
                acc = None
                for k in range(a.ncols):
                    p = _smul(a.get(i, k), b.get(k, j))
                    acc = p if acc is None else add(acc, p)
                out.append(acc)
        return Matrix(a.nrows, b.ncols, out)
    return _elementwise(a, b, _smul)


def div(a, b):
    if isinstance(b, Matrix):
        if isinstance(a, Matrix):
            return mul(a, inverse(b))
        return mul(a, inverse(b))

    def f(x, y):
        if y.value == 0:
            raise err("div_zero")
        return Q(x.value / y.value, dims_sub(x.dims, y.dims))

    return _elementwise(a, b, f)


def power(a, b):
    if isinstance(a, Matrix):
        n = need_int(b)
        if a.nrows != a.ncols:
            raise err("not_square")
        if n < 0:
            a, n = inverse(a), -n
        result = identity(a.nrows)
        for _ in range(n):
            result = mul(result, a)
        return result
    x = need_scalar(a)
    y = need_scalar(b)
    if not y.dimensionless:
        raise err("units_in_exponent")
    yv = y.value
    if x.value == 0 and yv == 0:
        raise err("uncertainty")  # observed: 0^0
    if x.value == 0 and (isinstance(yv, complex) or yv < 0):
        raise err("div_zero")
    try:
        if isinstance(x.value, complex) or isinstance(yv, complex) or (x.value < 0 and yv != int(yv)):
            v = complex(x.value) ** complex(yv)
        else:
            v = x.value ** yv
    except OverflowError:
        raise err("overflow")  # observed: 10^400
    if isinstance(v, float) and math.isinf(v) and not math.isinf(x.value if not isinstance(x.value, complex) else 0):
        raise err("overflow")
    if not x.dimensionless and isinstance(yv, complex):
        raise err("must_be_real")
    dims = dims_scale(x.dims, yv.real if isinstance(yv, complex) else yv)
    return Q(v, dims)


def identity(n: int) -> Matrix:
    return Matrix(n, n, [Q(1.0 if i == j else 0.0) for i in range(n) for j in range(n)])


def determinant(m: Matrix):
    if m.nrows != m.ncols:
        raise err("not_square")
    n = m.nrows
    a = [[m.get(i, j) for j in range(n)] for i in range(n)]
    det = Q(1.0)
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(a[r][c].value))
        if a[piv][c].value == 0:
            return Q(0.0, dims_scale(a[0][0].dims, n) if n else NODIM)
        if piv != c:
            a[c], a[piv] = a[piv], a[c]
            det = neg(det)
        det = _smul(det, a[c][c])
        for r in range(c + 1, n):
            f = div(a[r][c], a[c][c])
            for k in range(c, n):
                a[r][k] = sub(a[r][k], _smul(f, a[c][k]))
    return det


def inverse(m: Matrix) -> Matrix:
    if m.nrows != m.ncols:
        raise err("not_square")
    n = m.nrows
    # Gauss-Jordan on the magnitudes; element (i,j) of the inverse carries
    # the reciprocal units of element (j,i).
    vals = [[m.get(i, j).value for j in range(n)] for i in range(n)]
    inv = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(vals[r][c]))
        if abs(vals[piv][c]) < 1e-300:
            raise err("singular")
        vals[c], vals[piv] = vals[piv], vals[c]
        inv[c], inv[piv] = inv[piv], inv[c]
        p = vals[c][c]
        vals[c] = [v / p for v in vals[c]]
        inv[c] = [v / p for v in inv[c]]
        for r in range(n):
            if r != c:
                f = vals[r][c]
                vals[r] = [x - f * y for x, y in zip(vals[r], vals[c])]
                inv[r] = [x - f * y for x, y in zip(inv[r], inv[c])]
    return Matrix(n, n, [Q(inv[i][j], dims_scale(m.get(j, i).dims, -1)) for i in range(n) for j in range(n)])


def transpose(m: Matrix) -> Matrix:
    return Matrix(m.ncols, m.nrows, [m.get(i, j) for j in range(m.ncols) for i in range(m.nrows)])


def compare(op: str, a, b):
    x, y = need_scalar(a), need_scalar(b)
    if x.dims != y.dims and op not in ("≡", "≠"):
        raise err("units_mismatch")
    xv, yv = x.value, y.value
    if op in ("≈", "≉"):
        # approximately equal: equal to 1e-10 relative (SMath "≈")
        close = x.dims == y.dims and abs(complex(xv) - complex(yv)) <= 1e-10 * max(1.0, abs(complex(xv)), abs(complex(yv)))
        return Q(1.0 if close == (op == "≈") else 0.0)
    if op in ("≡",):
        return Q(1.0 if (xv == yv and x.dims == y.dims) else 0.0)
    if op == "≠":
        return Q(1.0 if not (xv == yv and x.dims == y.dims) else 0.0)
    if isinstance(xv, complex) or isinstance(yv, complex):
        raise err("must_be_real")
    r = {"<": xv < yv, ">": xv > yv, "≤": xv <= yv, "≥": xv >= yv}[op]
    return Q(1.0 if r else 0.0)


def cross(a, b):
    """Cross product of two 3-vectors (SMath's × operator, Ctrl+8)."""
    if not (isinstance(a, Matrix) and isinstance(b, Matrix) and len(a.items) == 3 and len(b.items) == 3):
        raise err("matrix_size")
    x, y = a.items, b.items

    def m(p, q):
        return Q(p.value * q.value, dims_add(p.dims, q.dims))

    return Matrix.column([sub(m(x[1], y[2]), m(x[2], y[1])),
                          sub(m(x[2], y[0]), m(x[0], y[2])),
                          sub(m(x[0], y[1]), m(x[1], y[0]))])
