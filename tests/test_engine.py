"""Unit-aware parsing and evaluation."""

import pytest

from calcforge.core.engine import (EVALUATE, FUNCTION, Workspace, evaluate_source,
                                   parse_statement, transform)
from calcforge.core.units import Q_, format_number, format_quantity


def value_of(source, workspace=None):
    workspace = workspace or Workspace()
    statements = evaluate_source(source, workspace)
    return statements[-1]


def test_implicit_multiplication():
    assert transform("5 m") == "5 * m"
    assert transform("2(3+4)") == "2 * ( 3 + 4 )"
    assert transform("3 kN m") == "3 * kN * m"
    assert transform("a^2") == "a ** 2"


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
