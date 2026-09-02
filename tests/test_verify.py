"""The independent check.

The point of the verifier is to disagree with the page when the page is wrong,
so most of these tests break something on purpose and insist that it is found.
"""
import pytest

from calcforge.core.verify import (DISAGREEMENT, IMPLAUSIBLE, REDEFINED,
                                   SHADOWED, verify_document)
from calcforge.items.mathitem import MathItem
from calcforge.items.tableitem import TableItem

from tests.test_usability import drag


def add_calculation(window, source, x=80, y=80, width=320, height=90):
    window.select_tool("math")
    drag(window.view, x, y, x + width, y + height)
    item = window.view.editing_item()
    item._editor.setPlainText(source)
    window.view.end_item_edit()
    window.recalculate()
    return item


def kinds(result):
    return [p.kind for p in result.problems]


# ---------------------------------------------------------------------------
# agreement
# ---------------------------------------------------------------------------

def test_an_empty_document_has_nothing_to_check(window):
    result = verify_document(window.document)
    assert result.ok
    assert "Nothing to check" in result.summary()


def test_a_sound_sheet_re_derives_exactly(window):
    add_calculation(window, "w = 12 kN/m\nL = 6 m\nM = w*L^2/8\nV = w*L/2")
    result = verify_document(window.document)
    assert result.ok, [p.message for p in result.problems]
    assert result.confirmed == 4
    assert "every one agreed" in result.summary()


def test_a_long_sheet_re_derives_exactly(window):
    add_calculation(window, """gamma_conc = 25 kN/m^3
h_slab = 175 mm
g_slab = gamma_conc*h_slab
Q_k = 3 kPa
b_trib = 4.2 m
w_Ed = (1.35*g_slab + 1.5*Q_k)*b_trib
L_span = 7.5 m
M_Ed = w_Ed*L_span^2/8""", height=220)
    result = verify_document(window.document)
    assert result.ok, [p.message for p in result.problems]


def test_values_published_from_a_table_re_derive(window):
    window.select_tool("table")
    drag(window.view, 80, 80, 460, 200)
    table = window.view.active_table
    table.set_cell(0, 0, "q")
    table.set_cell(1, 0, "5 kPa")
    table.current = (1, 0)
    window.refresh_formula_bar(table)
    window.cell_name.setText("q_floor")
    window.commit_cell_name()
    window.view.deactivate_table()

    add_calculation(window, "b = 3 m\nw = q_floor*b", y=400)
    result = verify_document(window.document)
    assert result.ok, [p.message for p in result.problems]
    assert window.document.workspace.get("w").to("kN/m").magnitude == pytest.approx(15)


# ---------------------------------------------------------------------------
# disagreement
# ---------------------------------------------------------------------------

def test_a_stale_result_on_the_page_is_caught(window):
    """The page keeps a number the source no longer produces."""
    item = add_calculation(window, "a = 2 m\nb = a*3")
    item.statements[-1].result = item.statements[-1].result * 2      # tamper
    result = verify_document(window.document)
    assert DISAGREEMENT in kinds(result)
    message = [p.message for p in result.problems if p.kind == DISAGREEMENT][0]
    assert "the page shows" in message and "re-deriving gives" in message


def test_a_result_with_the_wrong_units_is_caught(window):
    item = add_calculation(window, "a = 2 m\nb = a*3")
    from calcforge.core.units import Q_
    item.statements[-1].result = Q_(6, "kN")                          # tamper
    result = verify_document(window.document)
    assert DISAGREEMENT in kinds(result)


def test_a_definition_that_went_missing_is_caught(window):
    item = add_calculation(window, "x = 5 m\ny = x*2")
    item.source = "y = x*2"                                           # x is gone
    result = verify_document(window.document)
    assert DISAGREEMENT in kinds(result)


# ---------------------------------------------------------------------------
# sanity checks
# ---------------------------------------------------------------------------

def test_a_name_defined_twice_is_reported(window):
    add_calculation(window, "L = 6 m", y=80, height=40)
    add_calculation(window, "L := 9 m", y=300, height=40)
    result = verify_document(window.document)
    assert REDEFINED in kinds(result)
    assert "the later one wins" in [p.message for p in result.problems
                                    if p.kind == REDEFINED][0]


def test_a_name_that_shadows_a_unit_is_reported(window):
    add_calculation(window, "kg := 5 m", height=40)
    result = verify_document(window.document)
    assert SHADOWED in kinds(result)


def test_a_greek_name_is_not_treated_as_a_unit(window):
    """sigma is a stress. It is not the Stefan-Boltzmann constant."""
    add_calculation(window, "sigma = 275 MPa\ngamma_M = 1.0\nrho = 25 kN/m^3")
    result = verify_document(window.document)
    assert SHADOWED not in kinds(result)
    assert result.ok, [p.message for p in result.problems]


def test_an_implausible_magnitude_is_questioned(window):
    add_calculation(window, "sigma_bad = 275 GPa*1e9")
    result = verify_document(window.document)
    assert IMPLAUSIBLE in kinds(result)
    assert "check the units" in [p.message for p in result.problems
                                 if p.kind == IMPLAUSIBLE][0]


def test_ordinary_engineering_values_are_never_questioned(window):
    add_calculation(window, """f_ck = 30 MPa
E_s = 200 GPa
L_beam = 12 m
t_slab = 175 mm
N_col = 2500 kN
M_beam = 450 kN*m
q_floor = 5 kPa
d_bar = 25 mm""", height=220)
    result = verify_document(window.document)
    assert IMPLAUSIBLE not in kinds(result)
    assert result.ok, [p.message for p in result.problems]


# ---------------------------------------------------------------------------
# through the window
# ---------------------------------------------------------------------------

def test_the_check_runs_from_the_menu_and_reports_in_the_status_bar(window):
    add_calculation(window, "w = 10 kN/m\nL = 5 m\nM = w*L^2/8")
    result = window.verify_document(quiet=True)
    assert result.ok
    assert "agreed" in window.status_hint.text()


def test_findings_reach_the_problems_panel(window):
    add_calculation(window, "L = 6 m", y=80, height=40)
    add_calculation(window, "L := 9 m", y=300, height=40)
    window.verify_document(quiet=True)
    assert any(p.kind == REDEFINED for p in window.problems_panel._problems)


def test_the_check_survives_a_document_it_cannot_evaluate(window):
    add_calculation(window, "x = ((((")
    window.verify_document(quiet=True)          # must not raise
    add_calculation(window, "y = undefined_thing*2", y=300)
    window.verify_document(quiet=True)


def test_a_scoped_block_is_verified_in_its_own_scope(window):
    add_calculation(window, "L = 6 m", y=80, height=40)
    block = add_calculation(window, "w = 12 kN/m\nM = w*L^2/8", y=300)
    block.setSelected(True)
    window.set_block_scope(True)
    result = verify_document(window.document)
    assert result.ok, [p.message for p in result.problems]


# ---------------------------------------------------------------------------
# the worked example that ships with the app
# ---------------------------------------------------------------------------

def test_the_worked_example_re_derives_exactly(window):
    """The document the app offers as an example has to survive its own check."""
    window.load_sample()
    result = verify_document(window.document)
    assert result.confirmed > 20, "the example barely calculates anything"
    assert result.ok, [f"{p.item_name} {p.where}: {p.message}" for p in result.problems]


def test_the_worked_example_has_no_evaluation_problems(window):
    from calcforge.core.problems import collect_problems

    window.load_sample()
    problems = collect_problems(window.document)
    assert problems == [], [f"{p.item_name} {p.where}: {p.message}" for p in problems]


def test_the_worked_example_still_re_derives_after_a_reload(window, tmp_path):
    from calcforge.core.document import Document
    from calcforge.io import project as project_io

    window.load_sample()
    path = str(tmp_path / "example.cfx")
    project_io.save_document(window.document, path)

    reopened = Document()
    project_io.load_document(reopened, path)
    window.document = reopened
    window.rebuild_scenes()

    result = verify_document(window.document)
    assert result.ok, [f"{p.item_name} {p.where}: {p.message}" for p in result.problems]


def test_the_worked_examples_numbers_are_the_ones_it_claims(window):
    """Spot-check the example against arithmetic done independently."""
    window.load_sample()
    workspace = window.document.workspace

    # Page 1: a 7.2 m beam under 19.2 kN/m
    assert workspace.get("L").to("m").magnitude == pytest.approx(7.2)
    assert workspace.get("w").to("kN/m").magnitude == pytest.approx(
        1.2 * 8.5 + 1.5 * 6)
    assert workspace.get("M_max").to("kN*m").magnitude == pytest.approx(
        19.2 * 7.2 ** 2 / 8)
    assert workspace.get("V_max").to("kN").magnitude == pytest.approx(19.2 * 7.2 / 2)

    # Page 2: the floor build-up published from the table
    q_floor = workspace.get("q_floor")
    expected = 0.150 * 24 + 0.060 * 22 + 0.025 * 18 + 0.5
    assert q_floor.to("kPa").magnitude == pytest.approx(expected, rel=1e-6)
