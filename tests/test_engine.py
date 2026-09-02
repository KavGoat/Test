"""Unit-aware parsing and evaluation."""

import pytest

from calcforge.core.engine import (DEFINE, EVALUATE, FUNCTION, Workspace,
                                   evaluate_source, parse_statement, transform)
from calcforge.core.units import Q_, format_number, format_quantity, ureg


def value_of(source, workspace=None):
    workspace = workspace or Workspace()
    statements = evaluate_source(source, workspace)
    return statements[-1]


def test_implicit_multiplication():
    # A number written against a unit is bracketed so that it stays one value.
    assert transform("5 m") == "( 5 * m )"
    assert transform("2(3+4)") == "2 * ( 3 + 4 )"
    assert transform("3 kN m") == "( 3 * kN * m )"
    assert transform("a^2") == "a ** 2"


def test_a_quantity_is_not_split_by_what_follows_it():
    """"6 m / 200 mm" is thirty — not "(6 m / 200) mm", which is nonsense."""
    assert transform("6 m / 200 mm") == "( 6 * m ) / ( 200 * mm )"
    assert transform("2 kN / 4 m") == "( 2 * kN ) / ( 4 * m )"
    assert value_of("6 m / 200 mm").result_text() == "30"
    assert value_of("1 kN / 1000 N").result_text() == "1"
    assert value_of("2 kN / 4 m").result_text() == "500 N/m"
    assert value_of("1 hectare / 10000 m^2").result_text() == "1"

    # …while an exponent is still an exponent, and a unit still spans its own
    # division: 24 kN/m^3 is a density, not 24 kN divided by a cubic metre of
    # something else.
    assert value_of("24 kN/m^3 * 200 mm").result.to("kPa").magnitude == pytest.approx(4.8)
    assert value_of("2^3 m").result.to("m").magnitude == pytest.approx(8)
    workspace = Workspace()
    modulus = evaluate_source("f_cm = 38 MPa\n"
                              "E_cm = 22*(f_cm/(10 MPa))^0.3 GPa", workspace)[-1]
    assert modulus.result.to("GPa").magnitude == pytest.approx(32.836, rel=1e-4)


def test_units_flow_through_arithmetic():
    statement = value_of("3 m * 4 m")
    assert statement.ok
    assert statement.result.to("m**2").magnitude == pytest.approx(12)


def test_definition_and_reuse():
    workspace = Workspace()
    evaluate_source("b := 300 mm\nd := 500 mm\nZ := b*d^2/6", workspace)
    assert workspace.get("Z").to("mm**3").magnitude == pytest.approx(12.5e6)


def test_display_unit_conversion():
    statement = value_of("5000 mm -> m")
    assert statement.result_text() == "5 m"


def test_function_definition_and_call():
    workspace = Workspace()
    statements = evaluate_source("M(x) := x^2\nM(4 m)", workspace)
    assert statements[0].kind == FUNCTION
    assert statements[1].result.to("m**2").magnitude == pytest.approx(16)


def test_plain_equals_defines():
    workspace = Workspace()
    evaluate_source("a = 5 kN", workspace)
    assert workspace.get("a").magnitude == 5


def test_trailing_equals_is_an_evaluation():
    statement = parse_statement("2+2 =")
    assert statement.kind == EVALUATE
    assert statement.expression == "2+2"


def test_dimension_error_is_friendly():
    statement = value_of("1 m + 1 kg")
    assert not statement.ok
    assert "Units do not match" in statement.error


def test_unknown_name_error():
    statement = value_of("nonsense_name * 2")
    assert not statement.ok
    assert "not defined" in statement.error


def test_comparison_returns_boolean():
    statement = value_of("5 MPa <= 250 MPa")
    assert statement.result is True


def test_lazy_conditional_avoids_division_by_zero():
    workspace = Workspace()
    statements = evaluate_source("x := 0\ny := if(x == 0, 0, 1/x)", workspace)
    assert statements[1].ok
    assert workspace.get("y") == 0


def test_degrees_and_trigonometry():
    assert value_of("sin(30 deg)").result == pytest.approx(0.5)
    assert value_of("atan(1) -> deg").result.magnitude == pytest.approx(45)


def test_matrix_operations():
    workspace = Workspace()
    statements = evaluate_source("A := matrix([[2,1],[1,3]])\ndet(A)", workspace)
    assert statements[1].result == pytest.approx(5)


def test_numeric_integration_with_units():
    workspace = Workspace()
    statements = evaluate_source("f(x) := x\nintegral(f, 0 m, 2 m)", workspace)
    assert statements[1].result.to("m**2").magnitude == pytest.approx(2)


def test_root_finding():
    workspace = Workspace()
    statements = evaluate_source("g(x) := x^2 - 4\nroot_of(g, 0, 5)", workspace)
    assert statements[1].result == pytest.approx(2, abs=1e-6)


def test_comment_only_line():
    assert parse_statement("# just a note").kind == "comment"


def test_unicode_operators():
    assert value_of("2 × 3 ÷ 6").result == pytest.approx(1)
    assert value_of("√(16)").result == pytest.approx(4)


def test_engineering_formatting():
    assert format_number(123456789.0, 4, "engineering") == "123.5·10⁶"
    assert format_quantity(Q_(1234.5, "kN*m"), 5) == "1234.5 kN·m"


def test_no_dangerous_names():
    statement = value_of("__import__('os')")
    assert not statement.ok


def test_workspace_dependencies():
    workspace = Workspace()
    evaluate_source("a := 2\nb := 3", workspace)
    assert workspace.dependencies("a*b + 1") == {"a", "b"}


def test_cancelling_units_reduce_to_a_plain_number():
    assert value_of("6 m/(200 mm)").result == pytest.approx(30)
    assert value_of("138 MPa/(355 MPa)").result == pytest.approx(0.3887, rel=1e-3)
    statement = value_of("285 kN*m/(300 mm*(540 mm)^2*32 MPa)")
    assert statement.result == pytest.approx(0.1018, rel=1e-3)


def test_angles_and_percent_are_not_flattened():
    theta = value_of("30 deg").result
    assert theta.units == ureg.degree and theta.magnitude == pytest.approx(30)
    assert value_of("2 rad").result.magnitude == pytest.approx(2)
    assert value_of("45 percent").result.magnitude == pytest.approx(45)


def test_real_units_are_left_alone():
    assert value_of("3 m*4 m").result.to("m**2").magnitude == pytest.approx(12)
    assert value_of("12 kN/m * 6 m").result.to("kN").magnitude == pytest.approx(72)


def test_explicit_display_unit_still_wins():
    assert value_of("6 m/(200 mm) -> percent").result.magnitude == pytest.approx(3000)


def test_results_choose_a_readable_unit():
    workspace = Workspace()
    statements = evaluate_source(
        "w = 12 kN/m\nL = 7.2 m\nM = w*L^2/8\nV = w*L/2\n"
        "Z = 896 cm^3\nf_y = 355 MPa\nsigma = M/Z\nq = 780 kN/(2.4 m*2.4 m)",
        workspace)
    shown = {s.name: s.result_text() for s in statements if s.name}
    assert shown["M"] == "77.76 kN·m"
    assert shown["V"] == "43.2 kN"
    assert shown["sigma"] == "86.79 MPa"
    assert shown["q"] == "135.4 kPa"


def test_lengths_switch_between_millimetres_and_metres():
    assert value_of("300 mm").result_text() == "300 mm"
    assert value_of("7200 mm").result_text() == "7.2 m"
    assert value_of("1500 m").result_text() == "1.5 km"


def test_a_value_typed_in_a_sensible_unit_keeps_it():
    assert value_of("896 cm^3").result_text() == "896 cm³"
    assert value_of("14100 cm^4").result_text() == "14100 cm⁴"
    assert value_of("355 MPa").result_text() == "355 MPa"


def test_imperial_input_is_never_converted():
    assert value_of("3 kip").result_text() == "3 kip"
    assert value_of("50 ksi").result_text() == "50 ksi"
    assert value_of("800 lbf*ft").result_text() == "800 lbf·ft"


def test_what_the_author_typed_is_what_they_see():
    """Rewriting an input's unit is limited to lengths, where it helps."""
    assert value_of("1500 kN").result_text() == "1500 kN"
    assert value_of("1470 cm^3").result_text() == "1470 cm³"
    assert value_of("1200 kPa").result_text() == "1200 kPa"
    assert value_of("2400 kN*m").result_text() == "2400 kN·m"
    # the one exception everybody expects
    assert value_of("7200 mm").result_text() == "7.2 m"
    assert value_of("300 mm").result_text() == "300 mm"


def test_inches_are_a_unit_not_a_python_keyword():
    """`in` is a reserved word, so "12 in" has to be handled deliberately."""
    assert value_of("12 in -> mm").result_text() == "304.8 mm"
    assert value_of("101 in^3").result_text() == "101 in³"
    workspace = Workspace()
    statements = evaluate_source("Z_x = 101 in^3\nF_y = 50 ksi\n"
                                 "M_n = 0.9*F_y*Z_x -> kip*ft", workspace)
    assert statements[-1].error == ""
    assert statements[-1].result.to("kip*ft").magnitude == pytest.approx(378.75)


def test_a_temperature_is_built_not_multiplied():
    """degC has an offset, so 20 degC is not 20 times anything."""
    assert value_of("20 degC -> K").result.to("K").magnitude == pytest.approx(293.15)
    assert value_of("20 degC -> degF").result.to("degF").magnitude == pytest.approx(68)
    assert value_of("293.15 K -> degC").result.to("degC").magnitude == pytest.approx(20)
    # a temperature *difference* is an ordinary multiplicative quantity
    thermal = evaluate_source("alpha = 12e-6/K\ndT = 35 K\nL = 30 m\n"
                              "dL = alpha*dT*L -> mm", Workspace())[-1]
    assert dL_value(thermal) == pytest.approx(12.6)


def dL_value(statement):
    return statement.result.to("mm").magnitude


def test_a_moment_is_not_shown_as_an_energy():
    assert value_of("355 MPa*896 cm^3").result_text() == "318.1 kN·m"
    assert value_of("12 kN*3 m").result_text() == "36 kN·m"
    assert value_of("1500 J").result_text() == "1500 J"      # as typed
    workspace = Workspace()
    energy = evaluate_source("P = 3 kW\nE = P*1.5 hr", workspace)[-1]
    assert energy.result_text() == "16.2 MJ"                 # computed: laddered


def test_plain_equals_defines_once_then_checks():
    workspace = Workspace()
    statements = evaluate_source("b = 300 mm\nb = 300 mm\nb = 400 mm", workspace)
    assert statements[0].kind == DEFINE
    assert statements[1].kind == EVALUATE and statements[1].result is True
    assert statements[2].kind == EVALUATE and statements[2].result is False
    assert workspace.get("b").to("mm").magnitude == pytest.approx(300)


def test_colon_forces_a_definition_over_an_existing_name():
    workspace = Workspace()
    evaluate_source("b = 300 mm\nb : 450 mm\nb := 500 mm", workspace)
    assert workspace.get("b").to("mm").magnitude == pytest.approx(500)


def test_reading_order_is_reset_between_passes():
    workspace = Workspace()
    evaluate_source("b = 300 mm", workspace)
    # a second pass over the same source must define again, not compare
    statements = evaluate_source("b = 400 mm", workspace)
    assert statements[0].kind == DEFINE
    assert workspace.get("b").to("mm").magnitude == pytest.approx(400)


def test_greek_variable_names_are_never_treated_as_units():
    """pint calls sigma a radiation constant; an engineer means a stress."""
    for name in ("sigma", "gamma", "mu", "alpha", "beta", "theta", "rho"):
        statement = value_of(f"{name}*2")
        assert not statement.ok, f"{name} resolved to a unit"
        assert "not defined" in statement.error


def test_psi_is_still_pounds_per_square_inch():
    assert value_of("2000 psi -> MPa").result.to("MPa").magnitude == pytest.approx(13.79,
                                                                                   rel=1e-3)


def test_a_name_the_document_defines_beats_a_unit():
    workspace = Workspace()
    workspace.declare({"m", "s"})
    statements = evaluate_source("total = m*2", workspace)
    assert not statements[0].ok and "not defined" in statements[0].error


# ---------------------------------------------------------------------------
# A result is printed only when the line asks for one
# ---------------------------------------------------------------------------

def test_a_line_without_a_trailing_equals_asks_for_nothing():
    from calcforge.core.engine import parse_statement
    assert parse_statement("M := w*L^2/8").show_result is False
    assert parse_statement("M := w*L^2/8 =").show_result is True
    assert parse_statement("M =").show_result is True
    assert parse_statement("M").show_result is False


def test_a_comparison_is_not_a_request_for_a_result():
    from calcforge.core.engine import parse_statement
    for line in ("a == b", "a <= b", "a >= b", "a != b", "a ≤ b"):
        statement = parse_statement(line)
        assert statement.show_result is False, line
        assert "b" in statement.expression


def test_the_request_survives_a_comment_and_a_unit_arrow():
    from calcforge.core.engine import parse_statement
    statement = parse_statement("M := w*L^2/8 =   # midspan")
    assert statement.show_result and statement.comment == "midspan"
    assert statement.expression == "w*L^2/8"

    for line in ("M := x → kN*m =", "M := x = → kN*m"):
        statement = parse_statement(line)
        assert statement.show_result, line
        assert statement.target_unit == "kN*m"
        assert statement.expression == "x"


def test_a_line_with_no_request_is_still_worked_out():
    """The value has to be there for the lines that use it, just not printed."""
    from calcforge.core.engine import Workspace, evaluate_source

    workspace = Workspace()
    statements = evaluate_source("L := 6 m\nw := 12 kN/m\nM := w*L^2/8\nM =",
                                 workspace, "block")
    quiet = statements[2]
    assert quiet.show_result is False
    assert quiet.result is not None                     # worked out all the same
    assert workspace.get("M").to("kN*m").magnitude == pytest.approx(54)
    assert statements[3].show_result is True


def test_a_check_answers_itself_without_being_asked():
    from calcforge.core.engine import Workspace, evaluate_source
    statements = evaluate_source("util := 0.4\nutil = 0.4", Workspace(), "block")
    check = statements[1]
    assert check.show_result is True
    assert check.result is True
