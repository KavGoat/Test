"""Using the app: a whole calculation sheet, and the awkward moments.

The rest of the suite tests one thing at a time. This drives the application
the way somebody sitting at it would — a heading, some inputs, a result, a
change of mind, a drawing, a table — because a hundred parts that each work
alone can still add up to something nobody would want to use.
"""
import os
import tempfile

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from calcforge.core.document import Document
from calcforge.io import project as project_io

from test_usability import (click, double_click, drag, hover, markups,
                            press_key, type_text)


# ---------------------------------------------------------------------------
# Writing a sheet from start to finish
# ---------------------------------------------------------------------------

def test_a_whole_calculation_sheet_from_a_blank_page(window):
    workspace = window.document.workspace

    # A heading, typed as prose. The quotation mark opens a line that is a
    # calculation until it is told otherwise, and Shift with the space bar
    # tells it: a plain space is refused, so that a stray one cannot throw a
    # half-typed expression away.
    window.view._last_scene_pos = QPointF(70, 70)
    press_key(window.view, Qt.Key_unknown, '"')
    assert window.view.editing_item() is not None, 'the " key opens a line'
    type_text(window.view, "Beam")
    press_key(window.view, Qt.Key_Space, " ", Qt.ShiftModifier)
    QApplication.processEvents()
    type_text(window.view, "B1 - bending check")
    window.view.end_item_edit()
    assert markups(window)[0].text() == "Beam B1 - bending check"

    # The inputs: one calculation, Enter between the lines.
    window.view._last_scene_pos = QPointF(70, 120)
    press_key(window.view, Qt.Key_unknown, "/")
    for line in ("b:=300mm", "d:=500mm", "fc:=25MPa"):
        assert window.view.editing_item() is not None
        type_text(window.view, line)
        press_key(window.view, Qt.Key_Return)
    window.view.end_item_edit()
    window.recalculate()
    for name in ("b", "d", "fc"):
        assert workspace.get(name) is not None, f"{name} was not defined"

    # A result, asked for with a trailing "=".
    window.view._last_scene_pos = QPointF(70, 260)
    press_key(window.view, Qt.Key_unknown, "/")
    type_text(window.view, "Z:=b*d^2/6=")
    window.view.end_item_edit()
    window.recalculate()
    assert workspace.get("Z").to("mm**3").magnitude == pytest.approx(12.5e6)

    # A change of mind, made by opening the line again and retyping it.
    inputs = [m for m in markups(window)
              if m.TYPE == "math" and m.source.startswith("b:=")]
    assert inputs, "the inputs are not there to be edited"
    block = inputs[0]
    middle = block.mapToScene(QPointF(block.local_rect().width() * 0.8,
                                      block.local_rect().height() / 2))
    double_click(window.view, middle.x(), middle.y())
    assert window.view.editing_item() is block
    block._editor.setPlainText("b := 400 mm")
    block.retypeset_live()
    window.view.end_item_edit()
    window.recalculate()
    assert workspace.get("Z").to("mm**3").magnitude == pytest.approx(400 * 500 ** 2 / 6)

    # And undone.
    window.undo_stack.undo()
    window.recalculate()
    assert workspace.get("b").to("mm").magnitude == pytest.approx(300)

    # A drawing beside it, and a measurement of it.
    window.select_tool("rect")
    drag(window.view, 600, 120, 800, 260)
    assert [m for m in markups(window) if m.TYPE == "rect"]
    window.select_tool("measure_length")
    drag(window.view, 600, 300, 800, 300)
    assert [m for m in markups(window) if m.TYPE == "measure"]

    # A table the sheet can read from, by the names at the top of its columns.
    window.select_tool("table")
    drag(window.view, 600, 380, 950, 520)
    table = window.view.active_table
    assert table is not None
    table.sheet.resize(3, 2)
    table.sheet.header_row = True
    for row, values in enumerate([["Dia", "Shear"], ["12 mm", "29.4 kN"],
                                  ["16 mm", "54.3 kN"]]):
        for col, value in enumerate(values):
            table.set_cell(row, col, value)
    table.table_name = "bolts"
    window.view.deactivate_table()
    window.recalculate()

    window.view._last_scene_pos = QPointF(70, 560)
    press_key(window.view, Qt.Key_unknown, "/")
    type_text(window.view, "V:=bolts(16mm,Dia,Shear)=")
    window.view.end_item_edit()
    window.recalculate()
    assert workspace.get("V").to("kN").magnitude == pytest.approx(54.3)

    # Saved and reopened, with everything still on it.
    path = os.path.join(tempfile.mkdtemp(), "sheet.cfx")
    project_io.save_document(window.document, path)
    reopened = Document()
    project_io.load_document(reopened, path)
    kept = sum(len(page.to_dict()["items"]) for page in reopened.pages)
    assert kept == len(markups(window))


# ---------------------------------------------------------------------------
# The awkward moments
# ---------------------------------------------------------------------------

def test_tool_letters_fall_silent_while_words_are_being_typed(window):
    """"quick cloud arrow" must not pick three tools on its way in."""
    window.select_tool("text")
    drag(window.view, 100, 100, 340, 150)
    type_text(window.view, "quick cloud arrow measure")

    box = window.view.editing_item()
    assert box.text() == "quick cloud arrow measure"
    assert window.view.tool_key in ("text", "select")
    window.view.end_item_edit()


def test_tool_letters_fall_silent_inside_a_calculation(window):
    window.view._last_scene_pos = QPointF(100, 250)
    press_key(window.view, Qt.Key_unknown, "/")
    type_text(window.view, "cap:=5kN")
    assert window.view.editing_item()._editor.toPlainText() == "cap:=5kN"
    window.view.end_item_edit()


def test_tool_letters_fall_silent_inside_a_cell(window):
    window.select_tool("table")
    drag(window.view, 600, 100, 900, 220)
    window.view.open_cell_editor()
    assert window.view._cell_editor is not None
    type_text(window.view, "cover")
    assert window.view._cell_editor.text() == "cover"
    window.view.close_cell_editor()
    window.view.deactivate_table()


def test_no_letter_on_bare_paper_leaves_anything_behind(window):
    """A keystroke picks a tool or does nothing; it never draws by itself."""
    before = len(markups(window))
    for character in "qwertyuiopasdfghjklzxcvbnm":
        window.select_tool("select")
        press_key(window.view, Qt.Key_unknown, character)
        press_key(window.view, Qt.Key_Escape)
    assert len(markups(window)) == before


def test_a_letter_still_picks_its_tool_when_nothing_is_being_typed(window):
    window.select_tool("select")
    press_key(window.view, Qt.Key_unknown, "c")
    assert window.view.tool_key == "cloud"
    press_key(window.view, Qt.Key_Escape)
    assert window.view.tool_key == "select"


@pytest.mark.parametrize("half_finished", ["callout", "polygon", "text"])
def test_escape_gets_out_of_whatever_was_started(window, half_finished):
    if half_finished == "callout":
        window.select_tool("callout")
        click(window.view, 200, 400)
        assert window.view._pending_anchor is not None
    elif half_finished == "polygon":
        window.select_tool("polygon")
        click(window.view, 300, 400)
        click(window.view, 360, 430)
        assert window.view._draft is not None
    else:
        window.select_tool("text")
        drag(window.view, 400, 400, 500, 440)
        type_text(window.view, "x")
        assert window.view.editing_item() is not None

    press_key(window.view, Qt.Key_Escape)
    assert window.view.tool_key == "select"
    assert window.view._pending_anchor is None
    assert window.view._draft is None
    assert window.view.editing_item() is None
    assert not window.scene.selectedItems()


def test_delete_removes_the_selection_and_undo_brings_it_back(window):
    window.select_tool("rect")
    drag(window.view, 1000, 600, 1100, 680)
    rect = markups(window)[-1]
    window.scene.clearSelection()
    rect.setSelected(True)
    count = len(markups(window))

    press_key(window.view, Qt.Key_Delete)
    assert len(markups(window)) == count - 1
    window.undo_stack.undo()
    assert len(markups(window)) == count


def test_the_pointer_is_an_arrow_over_bare_paper(window):
    window.select_tool("select")
    hover(window.view, 1200, 900)
    assert window.view.cursor().shape() == Qt.ArrowCursor


def test_a_page_thumbnail_does_not_resurrect_a_selection(window):
    """It draws the page without handles rather than clearing and restoring.

    Clearing and restoring is how a thumbnail — drawn from a queued refresh —
    put back a selection the reader had let go of in the meantime.
    """
    window.select_tool("rect")
    drag(window.view, 200, 200, 320, 280)
    rect = markups(window)[-1]
    window.scene.clearSelection()
    rect.setSelected(True)

    frame = window.view.frame()
    frame.render_image(dpi=18.0, for_print=False)
    assert rect.isSelected(), "the render must not clear what is selected"
    assert rect._handles_visible, "and must give the handles back"

    window.scene.clearSelection()
    frame.render_image(dpi=18.0, for_print=False)
    assert not window.scene.selectedItems(), "nor put a stale one back"
