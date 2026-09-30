"""Units are right: every factor is checked against the exact definitions
(NIST SP 811 / SI 2019, written down here from those definitions, not
taken from SMath's unit file), every dimension against the SI base units,
every SI-prefixed unit against its base, and the derived units against each
other (a newton really is a kg·m/s², a pascal a N/m², ...)."""
from __future__ import annotations

import math
from fractions import Fraction

import pytest

from markforge.calc.engine.evaluator import Context, Evaluator
from markforge.calc.engine.extra_units import ADDED
from markforge.calc.engine.linear import parse_text
from markforge.calc.engine.parser import parse_row
from markforge.calc.engine.unitdata import BASE, UNITS

# SI base unit exponents: m kg s A K mol cd
def D(m=0, kg=0, s=0, A=0, K=0, mol=0, cd=0):
    d = dict(m=m, kg=kg, s=s, A=A, K=K, mol=mol, cd=cd)
    return tuple(d.get(b, 0) for b in BASE)


LBF = Fraction("4.4482216152605")  # 0.45359237 kg x 9.80665 m/s^2, exact
IN = Fraction("0.0254")
NIST = {
    # length
    "m": (1, D(m=1)), "mm": (Fraction(1, 1000), D(m=1)), "cm": (Fraction(1, 100), D(m=1)),
    "km": (1000, D(m=1)), "μm": (Fraction(1, 10 ** 6), D(m=1)), "nm": (Fraction(1, 10 ** 9), D(m=1)),
    "in": (IN, D(m=1)), "ft": (12 * IN, D(m=1)), "yd": (36 * IN, D(m=1)), "mi": (63360 * IN, D(m=1)),
    "Angstrom": (Fraction(1, 10 ** 10), D(m=1)),
    # mass
    "kg": (1, D(kg=1)), "g": (Fraction(1, 1000), D(kg=1)), "mg": (Fraction(1, 10 ** 6), D(kg=1)),
    "t": (1000, D(kg=1)), "lb": (Fraction("0.45359237"), D(kg=1)), "oz": (Fraction("0.45359237") / 16, D(kg=1)),
    # time
    "s": (1, D(s=1)), "ms": (Fraction(1, 1000), D(s=1)), "min": (60, D(s=1)), "hr": (3600, D(s=1)),
    "day": (86400, D(s=1)),
    # force
    "N": (1, D(kg=1, m=1, s=-2)), "kN": (1000, D(kg=1, m=1, s=-2)), "MN": (10 ** 6, D(kg=1, m=1, s=-2)),
    "mN": (Fraction(1, 1000), D(kg=1, m=1, s=-2)), "lbf": (LBF, D(kg=1, m=1, s=-2)),
    "kgf": (Fraction("9.80665"), D(kg=1, m=1, s=-2)), "dyn": (Fraction(1, 10 ** 5), D(kg=1, m=1, s=-2)),
    "kip": (1000 * LBF, D(kg=1, m=1, s=-2)),
    # pressure / stress
    "Pa": (1, D(kg=1, m=-1, s=-2)), "kPa": (1000, D(kg=1, m=-1, s=-2)), "MPa": (10 ** 6, D(kg=1, m=-1, s=-2)),
    "GPa": (10 ** 9, D(kg=1, m=-1, s=-2)), "bar": (10 ** 5, D(kg=1, m=-1, s=-2)),
    "atm": (101325, D(kg=1, m=-1, s=-2)), "psi": (LBF / IN ** 2, D(kg=1, m=-1, s=-2)),
    "ksi": (1000 * LBF / IN ** 2, D(kg=1, m=-1, s=-2)), "hPa": (100, D(kg=1, m=-1, s=-2)),
    "torr": (Fraction(101325, 760), D(kg=1, m=-1, s=-2)),
    # energy, power
    "J": (1, D(kg=1, m=2, s=-2)), "kJ": (1000, D(kg=1, m=2, s=-2)), "MJ": (10 ** 6, D(kg=1, m=2, s=-2)),
    "Wh": (3600, D(kg=1, m=2, s=-2)), "kWh": (3600000, D(kg=1, m=2, s=-2)),
    "W": (1, D(kg=1, m=2, s=-3)), "kW": (1000, D(kg=1, m=2, s=-3)), "MW": (10 ** 6, D(kg=1, m=2, s=-3)),
    # electrical
    "A": (1, D(A=1)), "mA": (Fraction(1, 1000), D(A=1)), "C": (1, D(A=1, s=1)),
    "V": (1, D(kg=1, m=2, s=-3, A=-1)), "kV": (1000, D(kg=1, m=2, s=-3, A=-1)),
    "Ω": (1, D(kg=1, m=2, s=-3, A=-2)), "F": (1, D(kg=-1, m=-2, s=4, A=2)),
    "H": (1, D(kg=1, m=2, s=-2, A=-2)), "T": (1, D(kg=1, s=-2, A=-1)), "Wb": (1, D(kg=1, m=2, s=-2, A=-1)),
    "S": (1, D(kg=-1, m=-2, s=3, A=2)),
    # others
    "Hz": (1, D(s=-1)), "kHz": (1000, D(s=-1)), "K": (1, D(K=1)), "mol": (1, D(mol=1)),
    "kmol": (1000, D(mol=1)), "cd": (1, D(cd=1)), "L": (Fraction(1, 1000), D(m=3)),
    "mL": (Fraction(1, 10 ** 6), D(m=3)), "ha": (10 ** 4, D(m=2)),
    "acre": (Fraction("4046.8564224"), D(m=2)), "kat": (1, D(mol=1, s=-1)),
    "Gy": (1, D(m=2, s=-2)), "Sv": (1, D(m=2, s=-2)),
    "deg": (Fraction(1, 180), D()), "rad": (1, D()),  # deg checked as π/180 below
}


@pytest.mark.parametrize("name", sorted(NIST))
def test_unit_matches_exact_definition(name):
    assert name in UNITS, f"{name} missing"
    factor, dims, offset = UNITS[name]
    want, wdims = NIST[name]
    if name == "deg":
        want = math.pi / 180
    assert tuple(dims) == wdims, (name, dims, wdims)
    assert math.isclose(float(factor), float(want), rel_tol=1e-15), (name, factor, float(want))
    assert offset == 0


def test_temperature_offsets():
    # °C = K - 273.15, °F = (K - 273.15)·9/5 + 32
    for name, f, off in (("°C", 1, 273.15), ("°F", 5 / 9, 273.15 - 32 * 5 / 9)):
        if name in UNITS:
            factor, dims, offset = UNITS[name]
            assert tuple(dims) == D(K=1)
            assert math.isclose(factor, f, rel_tol=1e-15), name
            assert math.isclose(offset, off, rel_tol=1e-12), (name, offset, off)


# the SI prefixes, written down here (SI Brochure, table 7) - not the app's table
SI_PREFIXES = [("p", Fraction(1, 10 ** 12)), ("n", Fraction(1, 10 ** 9)), ("μ", Fraction(1, 10 ** 6)),
               ("m", Fraction(1, 10 ** 3)), ("c", Fraction(1, 100)), ("d", Fraction(1, 10)), ("da", 10),
               ("h", 100), ("k", 10 ** 3), ("M", 10 ** 6), ("G", 10 ** 9), ("T", 10 ** 12)]


@pytest.mark.parametrize("name", ADDED)
def test_prefixed_units_are_prefix_times_base(name):
    for sym, mult in sorted(SI_PREFIXES, key=lambda p: -len(p[0])):
        base = name[len(sym):]
        if name == "Wh" or (name.startswith(sym) and base in UNITS and (base not in ADDED or base == "Wh")):
            break
    else:
        pytest.fail(name)
    if name == "Wh":
        return
    f, d, o = UNITS[name]
    bf, bd, bo = UNITS[base]
    assert tuple(d) == tuple(bd)
    assert math.isclose(f, bf * float(mult), rel_tol=1e-15), (name, f, bf * float(mult))


def _q(text):
    ev = Evaluator()
    ev.start_clock()
    return ev.eval(parse_row(parse_text(text)), Context())


@pytest.mark.parametrize("a,b", [
    ("'N", "'kg*'m/'s^2"), ("'Pa", "'N/'m^2"), ("'J", "'N*'m"), ("'W", "'J/'s"), ("'C", "'A*'s"),
    ("'V", "'W/'A"), ("'Ω", "'V/'A"), ("'F", "'C/'V"), ("'S", "1/'Ω"), ("'Wb", "'V*'s"),
    ("'T", "'Wb/'m^2"), ("'H", "'Wb/'A"), ("'Hz", "1/'s"), ("'Gy", "'J/'kg"), ("'kat", "'mol/'s"),
    ("'MPa", "'N/'mm^2"), ("'kPa", "'kN/'m^2"), ("'kN", "1000*'N"), ("'GPa", "'kN/'mm^2"),
    ("'kWh", "3.6*'MJ"), ("'psi", "'lbf/'in^2"), ("'L", "'dm^3"), ("'ha", "(100*'m)^2"),
    ("'ksi", "1000*'psi"), ("'kip", "1000*'lbf"), ("'hr", "60*'min"), ("'day", "24*'hr"),
])
def test_derived_units_are_coherent(a, b):
    x, y = _q(a), _q(b)
    assert x.dims == y.dims, (a, b)
    assert math.isclose(x.value, y.value, rel_tol=1e-14), (a, b, x.value, y.value)


def test_every_unit_is_a_positive_finite_factor_with_integer_or_half_dims():
    for name, (f, d, o) in UNITS.items():
        assert math.isfinite(f) and f > 0, name
        for e in d:
            assert float(e) * 2 == int(float(e) * 2), (name, d)


def _shown_back(q, fmt):
    from markforge.calc.engine.display import display_quantity, display_text
    from markforge.calc.engine.verify import parse_shown, parse_unit_text

    text = display_text(display_quantity(q, fmt))
    x, unit = parse_shown(text)
    f, dims = parse_unit_text(unit)
    return text, x * f, dims, f


@pytest.mark.parametrize("engineering", [True, False])
def test_every_unit_displays_its_own_size(engineering):
    """Every unit in the table, shown as a result ('u =), reads back as
    exactly that unit: the shown number times the shown unit is the unit's
    size, with the same dimensions (this is what caught 'P = 0.1 P)."""
    from markforge.calc.engine.numformat import NumberFormat
    from markforge.calc.engine.units import Quantity
    from markforge.calc.engine.verify import _dims_of

    fmt = NumberFormat()
    fmt.engineering = engineering
    fmt.decimals = 15
    bad = []
    for name, (f, d, o) in UNITS.items():
        if o:
            continue
        for k in (1.0, 12.5, 3.7e-4, 4.2e7):
            text, back, dims, uf = _shown_back(Quantity(k * f, tuple(d)), fmt)
            if dims != _dims_of(tuple(d)) or not math.isclose(back, k * f, rel_tol=1e-12, abs_tol=uf * 5.01e-16):
                bad.append((name, k, text))
    assert not bad, bad[:20]
