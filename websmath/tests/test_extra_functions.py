"""Plugin functions (eigenvals, eigenvecs, fft, ifft, delta) against known
answers and against their defining properties on random matrices."""
from __future__ import annotations

import cmath
import random

import pytest

from websmath.engine.values import Matrix
from websmath.tests.test_proof_units import _q


def _vals(v):
    return [complex(x.value) for x in v.items]


def test_eigenvalues_known():
    assert _vals(_q("eigenvals(mat(2,1,1,2,2,2))")) == [1, 3]
    assert _vals(_q("eigenvals(mat(4,1,2,3,2,2))")) == pytest.approx([2, 5])
    w = _vals(_q("eigenvals(mat(0,-1,1,0,2,2))"))
    assert w == pytest.approx([-1j, 1j]) and w[0].real == 0 and w[1].real == 0  # no round-off noise
    m = _q("eigenvals(mat(2,0,0,3,2,2)*1'MPa)")
    assert [x.value for x in m.items] == pytest.approx([2e6, 3e6]) and m.items[0].dims == _q("'MPa").dims


def test_eigenvectors_known():
    v = _q("eigenvecs(mat(4,1,2,3,2,2))")
    assert _vals(v) == pytest.approx([-1 / 5 ** 0.5, 1 / 2 ** 0.5, 2 / 5 ** 0.5, 1 / 2 ** 0.5])


def test_mixed_units_and_non_square_are_errors():
    from websmath.engine.errors import SMathError

    with pytest.raises(SMathError):
        _q("eigenvals(mat(1,2,3,4,5,6,2,3))")
    with pytest.raises(SMathError):
        _q("eigenvals(mat(1'm,2,3,4,2,2))")


@pytest.mark.parametrize("seed", range(60))
def test_eigen_definition_on_random_matrices(seed):
    """A·v = λ·v for every eigenpair, unit vectors, and the eigenvalues sum to the trace."""
    rng = random.Random(seed)
    n = rng.randint(1, 5)
    sym = rng.random() < 0.5
    a = [[rng.uniform(-9, 9) for _ in range(n)] for _ in range(n)]
    if sym:
        a = [[(a[i][j] + a[j][i]) / 2 for j in range(n)] for i in range(n)]
    text = "mat(" + ",".join(f"{a[i][j]:.6f}" for i in range(n) for j in range(n)) + f",{n},{n})"
    a = [[float(f"{a[i][j]:.6f}") for j in range(n)] for i in range(n)]
    w = _vals(_q(f"eigenvals({text})"))
    v = _vals(_q(f"eigenvecs({text})"))
    assert abs(sum(w) - sum(a[i][i] for i in range(n))) < 1e-9 * max(1, n * 9)
    for k in range(n):
        vec = [v[i * n + k] for i in range(n)]
        assert abs(sum(abs(x) ** 2 for x in vec) - 1) < 1e-9
        for i in range(n):
            av = sum(a[i][j] * vec[j] for j in range(n))
            assert abs(av - w[k] * vec[i]) < 1e-8 * max(1, abs(w[k]))
        if sym:
            assert abs(w[k].imag) == 0


def test_fft_known_and_round_trip():
    assert _vals(_q("fft(mat(1,1,1,1,4,1))")) == [4, 0, 0, 0]
    assert _vals(_q("fft(mat(1,0,0,0,4,1))")) == [1, 1, 1, 1]
    rng = random.Random(3)
    xs = [round(rng.uniform(-5, 5), 3) for _ in range(7)]
    back = _vals(_q("ifft(fft(mat(" + ",".join(map(str, xs)) + ",7,1)))"))
    assert back == pytest.approx(xs)
    # against the definition X_k = sum x_n e^(-2πikn/N)
    got = _vals(_q("fft(mat(" + ",".join(map(str, xs)) + ",7,1))"))
    for k in range(7):
        want = sum(x * cmath.exp(-2j * cmath.pi * k * m / 7) for m, x in enumerate(xs))
        assert abs(got[k] - want) < 1e-9


def test_delta():
    assert _q("delta(0)").value == 1 and _q("delta(0.5)").value == 0
    assert _q("delta(3,3)").value == 1 and _q("delta(2,3)").value == 0
