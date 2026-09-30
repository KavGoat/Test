"""Scales, sizes and measurements use SMath's unit system (decision 1).

These pin the adapter in calcforge/core/units.py to the calculation engine: a
quantity here is the engine's SI value and dimensions, the unit names are
SMath's, and a label is written by the engine's own number formatter.
"""
import pytest

from calcforge.calc.engine.unitdata import UNITS
from calcforge.core.document import PageScale
from calcforge.core.units import (UNIT_MENU, Q_, convert, format_quantity, parse_unit,
                                  DimensionalityError)


def test_pint_is_gone():
    """No module in the application imports Pint; SMath's table is the only one."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[1] / "calcforge"
    offenders = [str(p) for p in root.rglob("*.py")
                 if re.search(r"^\s*(import|from)\s+pint\b", p.read_text(encoding="utf-8"), re.M)]
    assert offenders == []


@pytest.mark.parametrize("text, si, dims", [
    ("5 m", 5.0, "m"), ("1.5m", 1.5, "m"), ("10mm", 0.01, "m"), ("2 ft", 0.6096, "m"),
    ("3 in", 0.0762, "m"), ("1 mi", 1609.344, "m"),
])
def test_lengths_read_as_the_engine_reads_them(text, si, dims):
    q = parse_unit(text)
    assert q.check("[length]")
    assert q.si == pytest.approx(si, rel=1e-15)
    assert q.engine_quantity().dims == tuple(UNITS["m"][1])


@pytest.mark.parametrize("text", ["10 lc", "//", "", "kN/", "5 5", "m^", "(m", "-", "5 h2o"])
def test_what_is_not_a_unit_is_none_never_an_exception(text):
    assert parse_unit(text) is None


def test_every_menu_unit_is_in_smaths_table():
    for group, units in UNIT_MENU.items():
        for unit in units:
            q = parse_unit(unit)
            assert q is not None, (group, unit)
            for name, _power in q.units.parts:
                assert name in UNITS, (group, unit, name)


def test_the_menus_use_smaths_names():
    flat = [u for units in UNIT_MENU.values() for u in units]
    for pint_only in ("pcf", "klf", "plf", "degC", "degF", "kelvin", "year", "mile"):
        assert pint_only not in flat
    for smath in ("°C", "°F", "K", "yr", "hr", "lbf/ft^3", "kip/ft", "lbf/ft"):
        assert smath in flat
    # h is Planck's constant in SMath's table; the hour is hr
    assert "h" not in flat


def test_the_written_out_imperial_loads_are_the_old_units():
    lbf, ft = UNITS["lbf"][0], UNITS["ft"][0]
    assert parse_unit("1 lbf/ft^3").si == pytest.approx(lbf / ft ** 3, rel=1e-15)   # pcf
    assert parse_unit("1 kip/ft").si == pytest.approx(1000 * lbf / ft, rel=1e-12)   # klf
    assert parse_unit("1 lbf/ft").si == pytest.approx(lbf / ft, rel=1e-15)          # plf


@pytest.mark.parametrize("value, unit, digits, text", [
    (2.4, "m", 2, "2.40 m"), (1000, "mm", 2, "1000.00 mm"), (30, "mm", 2, "30.00 mm"),
    (4.5, "m^2", 2, "4.50 m²"), (0.9, "m^3", 3, "0.900 m³"), (45.2, "kN*m", 1, "45.2 kN·m"),
    (1, "kN/m^2", 2, "1.00 kN/m²"), (30, "deg", 2, "30.00 deg"), (20, "°C", 1, "20.0 °C"),
    (123456, "mm", 2, "123456.00 mm"),
])
def test_labels_are_written_with_a_dot_and_superscripts(value, unit, digits, text):
    assert format_quantity(Q_(value, unit), digits, "fixed") == text


def test_a_label_rounds_exactly_as_an_equation_does():
    """Both go through the engine's formatter: half to even on the binary value."""
    from calcforge.calc.engine.numformat import NumberFormat, format_real
    for x in (2.345, 2.355, 0.125, 0.375, 1.0005, 99.995):
        shown = format_real(x, NumberFormat(decimals=2, trailing_zeros=True, threshold=15))
        assert format_quantity(Q_(x, "m"), 2, "fixed") == shown.mantissa + " m"


def test_conversions_agree_with_the_unit_table():
    assert convert(Q_(2400, "mm"), "m").magnitude == pytest.approx(2.4, rel=1e-15)
    assert Q_(100, "°C").to("°F").magnitude == pytest.approx(212, rel=1e-12)
    assert Q_(0, "°C").to("K").magnitude == pytest.approx(273.15, rel=1e-15)
    assert (Q_(5, "m") / Q_(2, "mm")).to("dimensionless").magnitude == pytest.approx(2500)
    with pytest.raises(DimensionalityError):
        Q_(1, "m").to("kg")


def test_a_volume_from_an_area_and_a_depth_reads_in_one_unit():
    volume = (Q_(4.5, "m^2") * parse_unit("200 mm")).to_reduced_units()
    assert format_quantity(volume, 3, "fixed") == "0.900 m³"


@pytest.mark.parametrize("stored", [
    {"magnitude": 17.6388888, "units": "mm"},                  # MarkForge wrote short names
    {"magnitude": 17.6388888, "units": "millimeter"},          # and Pint's long ones
    {"magnitude": 0.0176388888, "units": "meter"},
])
def test_a_scale_saved_by_calcforge_still_opens(stored):
    scale = PageScale.from_dict(dict(stored, label="1:50", calibrated=True))
    assert scale.ratio() == pytest.approx(50, rel=1e-6)


def test_a_scale_round_trips():
    scale = PageScale.from_ratio(200, "mm")
    again = PageScale.from_dict(scale.to_dict())
    assert again.ratio() == pytest.approx(200, rel=1e-15)
    assert again.display_unit == "mm"
