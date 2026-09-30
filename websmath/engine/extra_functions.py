"""Functions SMath Studio desktop gets from its bundled plugins rather than
its core list: eigenvals, eigenvecs, fft, ifft and delta.

They are computed with numpy (LAPACK's eigen-solvers, a standard FFT), not
hand-written algorithms, so the numbers are as reliable as the library.
"""
from __future__ import annotations

import numpy as np

from .builtins import _flat, _mat, _out, fn
from .catalog import FUNCTIONS
from .errors import err
from .units import NODIM
from .values import Matrix, Q, need_scalar

# not in SMath's core list (nor SMath Cloud's autocomplete); listed here so they complete
PLUGIN_FUNCTIONS = {"eigenvals", "eigenvecs", "fft", "ifft", "delta"}

FUNCTIONS.extend([
    ("eigenvals", 1, "Matrix and vector",
     'eigenvals("matrix") — Returns the eigenvalues of a square matrix as a vector, in ascending order.'),
    ("eigenvecs", 1, "Matrix and vector",
     'eigenvecs("matrix") — Returns a matrix whose columns are the unit eigenvectors, in the order of eigenvals.'),
    ("fft", 1, "Unknown", 'fft("vector") — Discrete Fourier transform of a vector.'),
    ("ifft", 1, "Unknown", 'ifft("vector") — Inverse discrete Fourier transform: ifft(fft(v)) = v.'),
    ("delta", 1, "Unknown", 'delta("number") — 1 when the number is zero, otherwise 0.'),
    ("delta", 2, "Unknown", 'delta("number", "number") — Kronecker delta: 1 when the numbers are equal, otherwise 0.'),
])


def _square(m) -> tuple:
    """(complex array, common dims) of a square matrix whose elements share one unit."""
    mm = _mat(m)
    if mm.nrows != mm.ncols:
        raise err("not_square")
    items = [need_scalar(x) for x in mm.items]
    dims = items[0].dims
    if any(x.dims != dims for x in items):
        raise err("units_mismatch")
    a = np.array([complex(x.value) for x in items]).reshape(mm.nrows, mm.ncols)
    if not np.all(np.isfinite(a)):
        raise err("cannot_evaluate")
    return a, dims


def _real_symmetric(a) -> bool:
    return bool(np.allclose(a.imag, 0) and np.allclose(a.real, a.real.T, rtol=1e-12, atol=1e-14 * max(1.0, np.abs(a).max())))


def _eigen(m):
    a, dims = _square(m)
    if _real_symmetric(a):
        w, v = np.linalg.eigh(a.real)  # symmetric: real eigenvalues, orthonormal vectors
        w, v = w.astype(complex), v.astype(complex)
    else:
        w, v = np.linalg.eig(a)
    # round-off (relative to the matrix's size) is exactly zero: [[0,-1],[1,0]] gives ±i, not 2.8·10^-17-i
    tiny = 1e-13 * max(1e-300, float(np.abs(a).max()))
    w = np.array([complex(0.0 if abs(x.real) < tiny else x.real, 0.0 if abs(x.imag) < tiny else x.imag) for x in w])
    order = sorted(range(len(w)), key=lambda k: (round(w[k].real, 12), round(w[k].imag, 12)))
    w, v = w[order], v[:, order]
    # unit length, and the largest component made positive real (a unique choice of sign/phase)
    for k in range(v.shape[1]):
        col = v[:, k]
        col = col / np.linalg.norm(col)
        j = int(np.argmax(np.abs(col)))
        col = col * (abs(col[j]) / col[j])
        col = np.array([complex(0.0 if abs(x.real) < 1e-13 else x.real, 0.0 if abs(x.imag) < 1e-13 else x.imag)
                        for x in col])
        v[:, k] = col
    return w, v, dims


@fn("eigenvals")
def _eigenvals(m):
    w, _v, dims = _eigen(m)
    return Matrix.column([_out(complex(x), dims) for x in w])


@fn("eigenvecs")
def _eigenvecs(m):
    _w, v, _dims = _eigen(m)
    n = v.shape[0]
    return Matrix(n, n, [_out(complex(v[i, j])) for i in range(n) for j in range(n)])


def _vector(v) -> tuple:
    items = _flat([v])
    dims = items[0].dims
    if any(x.dims != dims for x in items):
        raise err("units_mismatch")
    return np.array([complex(x.value) for x in items]), dims


@fn("fft")
def _fft(v):
    a, dims = _vector(v)
    return Matrix.column([_out(complex(x), dims) for x in np.fft.fft(a)])


@fn("ifft")
def _ifft(v):
    a, dims = _vector(v)
    return Matrix.column([_out(complex(x), dims) for x in np.fft.ifft(a)])


@fn("delta")
def _delta1(x):
    return Q(1.0 if need_scalar(x).value == 0 else 0.0)


@fn("delta", 2)
def _delta2(a, b):
    x, y = need_scalar(a), need_scalar(b)
    if x.dims != y.dims:
        raise err("units_mismatch")
    return Q(1.0 if x.value == y.value else 0.0, NODIM)
