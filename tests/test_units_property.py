"""Properties that must hold for every value, on every sheet, every time.

The worked examples in test_validation.py check answers that are known.  This
file checks the things that have to be true of *all* answers: that choosing a
unit to display in never changes the value, that a conversion and its inverse
come back to where they started, that the same calculation written in different
units agrees, and that incompatible units are refused rather than fudged.

These are the failures that would put a wrong number on a drawing without
anybody noticing, so they are checked by exhaustion and by random sampling
rather than by example.
"""
import itertools
import math
import random

import pytest

from calcforge.core.engine import Workspace, evaluate_source
from calcforge.core.units import (Q_, Quantity, convert, format_quantity,
                                  normalise_for_display, parse_unit,
                                  preferred_unit, simplify_units)

# Units grouped by what they measure.  Anything in one group converts to
# anything else in the same group; nothing converts across groups.
FAMILIES = {
    "length": ["mm", "cm", "m", "km", "in", "ft", "yd", "mile"],
    "area": ["mm^2", "cm^2", "m^2", "in^2", "ft^2", "hectare"],
    "volume": ["mm^3", "cm^3", "m^3", "litre", "in^3", "ft^3"],
    "force": ["N", "kN", "MN", "lbf", "kip"],
    "stress": ["Pa", "kPa", "MPa", "GPa", "psi", "ksi", "N/mm^2"],
    "line_load": ["N/m", "kN/m", "plf", "klf"],
    "density": ["kg/m^3", "tonne/m^3", "lb/ft^3"],
    "unit_weight": ["N/m^3", "kN/m^3", "pcf"],
    "moment": ["N*m", "kN*m", "MN*m", "lbf*ft", "kip*ft"],
    "mass": ["g", "kg", "tonne", "lb"],
    "time": ["s", "min", "hour", "day"],
    "velocity": ["m/s", "km/h", "ft/s", "mph"],
}

MAGNITUDES = [1e-6, 1e-3, 0.25, 1.0, 7.0, 123.456, 1000.0, 98765.4321, 1e9]


def pairs(family):
    return list(itertools.permutations(FAMILIES[family], 2))


# ---------------------------------------------------------------------------
# a conversion and its inverse
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_every_conversion_within_a_family_round_trips(family):
    """a -> b -> a returns the number it started with."""
    for source, target in pairs(family):
        for magnitude in (1.0, 137.0, 0.004):
            start = Q_(magnitude, source.replace("^", "**"))
            there = convert(start, target)
            back = convert(there, source)
            assert float(back.to(start.units).magnitude) == pytest.approx(
                magnitude, rel=1e-9), f"{magnitude} {source} -> {target} -> {source}"


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_conversion_never_changes_the_physical_value(family):
    """Whatever unit it is read in, it is the same quantity underneath."""
    for source, target in pairs(family):
        start = Q_(3.7, source.replace("^", "**"))
        moved = convert(start, target)
        assert moved.to_base_units().magnitude == pytest.approx(
            start.to_base_units().magnitude, rel=1e-9)


# ---------------------------------------------------------------------------
# display never changes the value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_choosing_a_display_unit_leaves_the_value_alone(family):
    """The automatic unit choice is cosmetic; the number behind it is not."""
    for unit in FAMILIES[family]:
        for magnitude in MAGNITUDES:
            original = Q_(magnitude, unit.replace("^", "**"))
            shown = normalise_for_display(original)
            assert shown.to_base_units().magnitude == pytest.approx(
                original.to_base_units().magnitude, rel=1e-12), f"{magnitude} {unit}"


def test_the_preferred_unit_is_always_one_the_value_can_convert_to():
    for family, units in FAMILIES.items():
        for unit in units:
            value = Q_(42.0, unit.replace("^", "**"))
            chosen = preferred_unit(value)
            if chosen is None:
                continue
            converted = value.to(chosen)
            assert converted.to_base_units().magnitude == pytest.approx(
                value.to_base_units().magnitude, rel=1e-12)


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_what_is_printed_reads_back_as_the_same_number(family):
    """Round-trip through the text an engineer actually sees on the page."""
    for unit in FAMILIES[family]:
        for magnitude in (1.0, 42.5, 987.25, 0.125):
            value = Q_(magnitude, unit.replace("^", "**"))
            text = format_quantity(value, 10)
            reparsed = parse_unit(text.replace("·", "*"))
            assert isinstance(reparsed, Quantity), text
            assert reparsed.to_base_units().magnitude == pytest.approx(
                value.to_base_units().magnitude, rel=1e-8), text


# ---------------------------------------------------------------------------
# the same sum, written in different units
# ---------------------------------------------------------------------------

SAME_ANSWER = [
    # (source, name, unit, expected)
    ("w = 12 kN/m\nL = 6 m\nM = w*L^2/8", "M", "kN*m", 54.0),
    ("w = 12000 N/m\nL = 6000 mm\nM = w*L^2/8", "M", "kN*m", 54.0),
    ("w = 12 kN/m\nL = 600 cm\nM = w*L^2/8", "M", "kN*m", 54.0),
    ("w = 0.012 MN/m\nL = 0.006 km\nM = w*L^2/8", "M", "kN*m", 54.0),
]


@pytest.mark.parametrize("source,name,unit,expected", SAME_ANSWER)
def test_the_units_a_sheet_is_written_in_do_not_change_its_answer(
        source, name, unit, expected):
    workspace = Workspace()
    workspace.begin_pass()
    evaluate_source(source, workspace, "t")
    assert float(workspace.get(name).to(unit).magnitude) == pytest.approx(expected)


def test_an_imperial_sheet_and_a_metric_sheet_agree():
    metric = Workspace()
    metric.begin_pass()
    evaluate_source("P = 100 kN\nA = 0.05 m^2\nsigma = P/A", metric, "t")

    imperial = Workspace()
    imperial.begin_pass()
    evaluate_source("P = 22.4809 kip\nA = 77.5 in^2\nsigma = P/A", imperial, "t")

    assert float(imperial.get("sigma").to("MPa").magnitude) == pytest.approx(
        float(metric.get("sigma").to("MPa").magnitude), rel=2e-3)


# ---------------------------------------------------------------------------
# incompatible units are refused
# ---------------------------------------------------------------------------

NONSENSE = [
    "6 m + 5 kN",
    "3 kg - 2 m",
    "10 kPa + 4 m^2",
    "5 s + 1 kN/m",
    "2 m^2 + 3 m^3",
    "1 kN*m + 1 kN",
]


@pytest.mark.parametrize("source", NONSENSE)
def test_adding_unlike_quantities_is_an_error_not_a_number(source):
    workspace = Workspace()
    workspace.begin_pass()
    statement = evaluate_source(f"x = {source}", workspace, "t")[0]
    assert statement.error, f"{source} was accepted and gave {statement.result}"
    assert workspace.get("x") is None


BAD_CONVERSIONS = [("5 kN", "m"), ("2 m", "kg"), ("7 MPa", "s"), ("1 m^2", "m^3")]


@pytest.mark.parametrize("source,unit", BAD_CONVERSIONS)
def test_converting_to_the_wrong_dimension_is_an_error(source, unit):
    workspace = Workspace()
    workspace.begin_pass()
    statement = evaluate_source(f"x = {source} -> {unit}", workspace, "t")[0]
    assert statement.error


def test_comparing_unlike_quantities_is_an_error():
    workspace = Workspace()
    workspace.begin_pass()
    statement = evaluate_source("check = 5 kN <= 3 m", workspace, "t")[0]
    assert statement.error


# ---------------------------------------------------------------------------
# ratios cancel to plain numbers
# ---------------------------------------------------------------------------

RATIOS = [
    ("6 m / 200 mm", 30.0),
    ("1 kN / 1000 N", 1.0),
    ("250 kN*m/(1500 cm^3 * 355 MPa)", 250e3 / (1500e-6 * 355e6)),
    ("50 ksi / 344.7378645 MPa", 1.0),
    ("1 hectare / 10000 m^2", 1.0),
]


@pytest.mark.parametrize("source,expected", RATIOS)
def test_a_ratio_comes_out_as_a_plain_number(source, expected):
    workspace = Workspace()
    workspace.begin_pass()
    statement = evaluate_source(f"r = {source}", workspace, "t")[0]
    assert statement.error == ""
    result = simplify_units(statement.result)
    number = float(result.magnitude if isinstance(result, Quantity) else result)
    assert number == pytest.approx(expected, rel=1e-6)
    if isinstance(result, Quantity):
        assert result.dimensionless


# ---------------------------------------------------------------------------
# random sheets
# ---------------------------------------------------------------------------

def test_a_thousand_random_conversions_hold_their_value():
    """Fuzz the conversion machinery against pint's own arithmetic."""
    generator = random.Random(20260902)
    for _ in range(1000):
        family = generator.choice(sorted(FAMILIES))
        source, target = generator.sample(FAMILIES[family], 2)
        magnitude = generator.choice([
            generator.uniform(1e-4, 1e-1), generator.uniform(0.1, 10),
            generator.uniform(10, 1e4), generator.uniform(1e4, 1e8),
        ])
        start = Q_(magnitude, source.replace("^", "**"))
        ours = convert(start, target)
        theirs = start.to(target.replace("^", "**"))
        assert float(ours.to(theirs.units).magnitude) == pytest.approx(
            float(theirs.magnitude), rel=1e-9), f"{magnitude} {source} -> {target}"


def test_random_arithmetic_agrees_with_plain_pint():
    """Whatever the engine does to an expression, the physics is unchanged."""
    generator = random.Random(4711)
    operations = ["*", "/"]
    for _ in range(400):
        a_unit = generator.choice(FAMILIES["force"])
        b_unit = generator.choice(FAMILIES["length"])
        a = round(generator.uniform(0.5, 500), 4)
        b = round(generator.uniform(0.5, 500), 4)
        operation = generator.choice(operations)
        workspace = Workspace()
        workspace.begin_pass()
        statement = evaluate_source(
            f"x = {a} {a_unit} {operation} ({b} {b_unit})", workspace, "t")[0]
        assert statement.error == "", statement.raw
        expected = eval(f"Q_({a}, {a_unit.replace('^', '**')!r}) {operation} "
                        f"Q_({b}, {b_unit.replace('^', '**')!r})", {"Q_": Q_})
        assert statement.result.to_base_units().magnitude == pytest.approx(
            expected.to_base_units().magnitude, rel=1e-9)


def test_random_sheets_are_order_independent_in_value():
    """Renaming and reordering independent lines cannot change the answers."""
    generator = random.Random(99)
    for _ in range(200):
        w = round(generator.uniform(1, 50), 3)
        span = round(generator.uniform(2, 12), 3)
        first = Workspace()
        first.begin_pass()
        evaluate_source(f"w = {w} kN/m\nL = {span} m\nM = w*L^2/8", first, "t")
        second = Workspace()
        second.begin_pass()
        evaluate_source(f"L = {span} m\nw = {w} kN/m\nM = w*L^2/8", second, "t")
        assert float(first.get("M").to("kN*m").magnitude) == pytest.approx(
            float(second.get("M").to("kN*m").magnitude), rel=1e-12)


# ---------------------------------------------------------------------------
# numbers that are hard to print
# ---------------------------------------------------------------------------

AWKWARD = [1e-12, 1e-6, 0.1, 1 / 3, 2 / 3, 1e6 - 0.5, 1e12, 6.02214076e23,
           -0.0001, -12345.6789]


@pytest.mark.parametrize("magnitude", AWKWARD)
def test_awkward_magnitudes_survive_the_display_path(magnitude):
    value = Q_(magnitude, "N")
    shown = normalise_for_display(value)
    assert shown.to("N").magnitude == pytest.approx(magnitude, rel=1e-12)
    text = format_quantity(shown, 12)
    assert text and "nan" not in text.lower()


def test_zero_and_infinity_do_not_break_the_unit_chooser():
    for magnitude in (0.0, math.inf, -math.inf, math.nan):
        value = Q_(magnitude, "kN")
        assert preferred_unit(value) is None
        assert format_quantity(value, 4)          # must not raise
