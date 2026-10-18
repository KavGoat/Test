"""The Properties toolbar and the Properties panel for every kind of markup,
against the user's Revu 21 screenshots (docs/qa/revu_shots/propbar/) — the
user, 2026-10-18: "Make sure the property toolbar for each markup type has
the important controls, heads and sizes, line styles, hatches, colour,
thickness, fills etc … Make sure that the Properties panel has all the items
for each markup type."

Each kind is drawn with the mouse, picked with the mouse, and the bar's
visible controls and the panel's Appearance rows are read in order: a
control missing or one too many fails by name.
"""
from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QComboBox,
                               QFormLayout, QLabel, QPushButton, QRadioButton, QWidget)

from tests.test_propbar_gaps import (click, drag, ink_in, key, markups, menu_click, page,
                                     pick, pump, save_and_reopen, scaled, select, shown_on_bar)


# ---------------------------------------------------------------------------
# reading the bar and the panel
# ---------------------------------------------------------------------------
def bar_widgets(w) -> list:
    """The bar's visible controls, left to right: a label as its words, a
    control by its object name."""
    bar = w.style_bar
    out = []
    for action in bar.actions():
        if not action.isVisible() or action.isSeparator():
            continue
        widget = bar.widgetForAction(action)
        if widget is None:
            continue
        out.append(widget.text() if isinstance(widget, QLabel) else widget.objectName())
    return out


def _row_words(item) -> str:
    widget = item.widget() if item is not None else None
    if widget is None and item is not None and item.layout() is not None:
        holder = item.layout()
        texts = []
        for index in range(holder.count()):
            texts.append(_row_words(holder.itemAt(index)))
        return " ".join(t for t in texts if t)
    if widget is None:
        return ""
    found = [widget] if isinstance(widget, QAbstractButton) else []
    found += widget.findChildren(QAbstractButton)
    return " ".join(b.text() for b in found
                    if isinstance(b, (QCheckBox, QRadioButton, QPushButton)) and b.text())


def section_rows(w, title: str = "Appearance") -> list:
    """A panel section's rows in order: each row's label, or — a row with
    none — the words of its tick boxes and buttons."""
    from calcforge.ui.panels import PropertySection
    for section in w.properties_panel.findChildren(PropertySection):
        if section.title() != title or section.isHidden():
            continue
        form = section.form
        rows = []
        for row in range(form.rowCount()):
            label = form.itemAt(row, QFormLayout.LabelRole)
            words = label.widget().text() if label is not None and label.widget() else ""
            if not words:
                field = form.itemAt(row, QFormLayout.FieldRole) or \
                    form.itemAt(row, QFormLayout.SpanningRole)
                words = _row_words(field)
            if words:
                rows.append(words)
        return rows
    return []


def panel_rows(w) -> list:
    return section_rows(w, "Appearance")


def sections(w) -> list:
    from calcforge.ui.panels import PropertySection
    return [s.title() for s in w.properties_panel.findChildren(PropertySection)
            if not s.isHidden()]


def drawn(w, tool: str):
    """Draw one markup with *tool* the way a person does, then pick it."""
    from tests.test_every_command_is_bindable import _draw
    from tests.test_usability import markups as all_markups
    w.show()
    w.activateWindow()
    w.show_panel("dock_properties", True)
    pump()
    before = {id(i) for i in all_markups(w)}
    _draw(w, tool, 120, 140, 260, 230)
    new = [i for i in all_markups(w) if id(i) not in before]
    assert new, f"{tool}: nothing drawn"
    item = new[0]
    w.select_tool("select")
    w.view.scene().clearSelection()
    item.setSelected(True)
    w.refresh_selection()
    pump(4)
    return item


# ---------------------------------------------------------------------------
# the tables, from the user's shots (and Revu 21's own panels)
# ---------------------------------------------------------------------------
LINE = ["Line:", "lineColour", "overallOpacity", "lineStyleBar", "lineWidth"]
ENDS = ["Start:", "lineEndStart", "End:", "lineEndEnd"]
FILL = ["Fill:", "fillColour", "fillOpacity"]
HATCH = ["Hatch:", "hatchPattern", "hatchColourBar"]
FONT = ["Font:", "fontFamily", "fontSize", "textColour", "fontStyle"]
TAIL = ["measureUnits", "measureCaption"]


P_LINE = ["Colour:", "Fill Colour:", "Opacity:", "Line Width:", "Style:", "Spacing:"]
P_ENDS = ["Start:", "End:", "Start Size:", "End Size:"]
P_SHAPE = ["Colour:", "Fill Colour:", "Hatch:", "Scale:", "Opacity:", "Fill Opacity:",
           "Hatch Opacity:", "Line Width:", "Style:", "Spacing:"]
P_FONT = ["Font:", "Font Size:", "Font Colour:", "Font Style:"]
SEG = ["Show Segment Values", "Align to Segment", "Align Horizontally"]
CAP = ["Show Caption Edit"]
CEN = ["Show Centroid"]
KIND = ["styleKindMenu"]
START_AUTO = ["Start:", "lineEndStart", "arrowStartSize", "End:", "lineEndEnd", "arrowSize",
              "lineEndFill"]

#: tool → (the bar's visible controls, the panel's Appearance rows), each kind
#: drawn as its tool draws it (an arrow with a Closed end, a measurement with
#: Closed ends both sides, a line with none).
KINDS = {
    # shot 08's highlighter: Line colour, %, width; the pen has no line ends
    "pen": (KIND + LINE + ["styleHighlight"], ["Colour:", "Opacity:", "Line Width:",
                                                "Style:", "Spacing:"]),
    "highlighter": (KIND + ["Line:", "lineColour", "overallOpacity", "lineWidth"],
                    ["Colour:", "Opacity:", "Line Width:"]),
    # shot 02: Start ▾ End ▾ with nothing on them: no Auto, no line-end colour
    "line": (KIND + LINE + ENDS + ["styleHighlight"], P_LINE + P_ENDS),
    # shot 09: End Closed, its Auto ▾ and the line-end colour swatch
    "arrow": (KIND + LINE + ENDS + ["arrowSize", "lineEndFill", "styleHighlight"],
              P_LINE + P_ENDS),
    "arc": (KIND + LINE + ENDS + ["styleHighlight"], P_LINE + P_ENDS),
    "polyline": (KIND + LINE + ENDS + ["styleHighlight"], P_LINE + P_ENDS),
    "rect": (KIND + LINE + ["Radius:", "cornerRadius"] + FILL + HATCH + ["styleHighlight"],
             P_SHAPE + ["Corner Radius:"]),
    "ellipse": (KIND + LINE + FILL + HATCH + ["styleHighlight"], P_SHAPE),
    # a closed shape: no Start/End
    "polygon": (KIND + LINE + FILL + HATCH + ["styleHighlight"], P_SHAPE),
    # shot 04: scallop style ▾, intensity ≋ ▾
    "cloud": (KIND + ["Line:", "lineColour", "overallOpacity", "lineStyleBar", "cloudSize",
                      "lineWidth"] + FILL + HATCH + ["styleHighlight"], P_SHAPE + ["Size:"]),
    "highlight": (KIND + ["overallOpacity"] + FILL, ["Fill Colour:", "Opacity:",
                                                     "Fill Opacity:"]),
    "redact": (KIND + LINE + FILL + HATCH + ["styleHighlight"], P_SHAPE),
    "link": (KIND + ["Line:", "lineColour"], ["Colour:"]),
    # a text box: Line, Fill, Font, size, A, colour, Style
    "text": (KIND + LINE + FILL + ["Font:", "fontFamily", "fontSize", "fontAuto",
                                   "textColour", "fontStyle"],
             ["Colour:", "Fill Colour:", "Opacity:", "Fill Opacity:", "Line Width:", "Style:",
              "Spacing:"] + P_FONT + ["Alignment:", "Margin:"]),
    # shot 03: End ▾ Auto ▾, Fill, Shape ▾, fit to text, Font … A, colour, Style
    "callout": (KIND + LINE + ["End:", "lineEndEnd", "arrowSize"] + FILL
                + ["Shape:", "calloutShapeBar", "fitToText", "Font:", "fontFamily", "fontSize",
                   "fontAuto", "textColour", "fontStyle"],
                ["Colour:", "Fill Colour:", "Opacity:", "Fill Opacity:", "Line Width:", "Style:",
                 "Spacing:", "End:", "End Size:", "Shape:"] + P_FONT + ["Alignment:", "Margin:"]),
    "cloud_callout": (KIND + ["Line:", "lineColour", "overallOpacity", "lineStyleBar",
                              "cloudSize", "lineWidth", "End:", "lineEndEnd", "arrowSize"] + FILL
                      + ["Shape:", "calloutShapeBar", "fitToText", "Font:", "fontFamily",
                         "fontSize", "fontAuto", "textColour", "fontStyle"],
                      ["Colour:", "Fill Colour:", "Opacity:", "Fill Opacity:", "Line Width:",
                       "Style:", "Spacing:", "Size:", "End:", "End Size:", "Shape:"] + P_FONT
                      + ["Alignment:", "Margin:"]),
    # Revu's note: Colour, opacity, Icon ▾
    "note": (KIND + ["Colour:", "noteColour", "noteOpacity", "Icon:", "noteIcon"],
             ["Icon:", "Colour:", "Fill Colour:", "Opacity:", "Fill Opacity:", "Line Width:",
              "Style:", "Spacing:"]),
    "stamp": (KIND + LINE + FILL + HATCH + ["styleHighlight"] + FONT, P_SHAPE + P_FONT),
    "flag": (KIND + ["Line:", "lineColour", "overallOpacity", "lineWidth"] + FILL
             + ["styleHighlight"],
             ["Colour:", "Fill Colour:", "Opacity:", "Fill Opacity:", "Line Width:"]),
    "contents": (KIND + ["Line:", "lineColour", "overallOpacity", "lineWidth"] + FILL
                 + ["styleHighlight", "Font:", "fontSize", "textColour", "fontStyle"],
                 ["Colour:", "Fill Colour:", "Opacity:", "Fill Opacity:", "Line Width:"]),
    # shot 05: Start Auto End Auto, the line-end colour, highlight, Units,
    # Caption, Font … Style, Totals
    "measure_length": (KIND + LINE + START_AUTO + ["styleHighlight"] + TAIL + FONT
                       + ["Totals:", "measureTotals"], P_LINE + P_ENDS + CAP + P_FONT),
    # shots 06/07: a dimension has no Units or Totals
    "measure_dimension": (KIND + LINE + START_AUTO + ["styleHighlight", "measureCaption"]
                          + FONT, P_LINE + P_ENDS + CAP + P_FONT),
    "measure_polylength": (KIND + LINE + START_AUTO + ["styleHighlight"] + TAIL + FONT
                           + ["Totals:", "measureTotals"],
                           P_LINE + P_ENDS + SEG + CAP + P_FONT),
    "measure_area": (KIND + LINE + FILL + HATCH + ["styleHighlight", "styleCutout"] + TAIL
                     + ["Totals:", "measureTotals"], P_SHAPE + SEG + CAP + CEN + P_FONT),
    "measure_perimeter": (KIND + LINE + FILL + ["styleHighlight"] + TAIL + FONT
                          + ["Totals:", "measureTotals"],
                          ["Colour:", "Fill Colour:", "Opacity:", "Fill Opacity:",
                           "Line Width:", "Style:", "Spacing:"] + SEG + CAP + CEN + P_FONT),
    "measure_volume": (KIND + LINE + FILL + HATCH + ["styleHighlight", "styleCutout"] + TAIL
                       + ["Totals:", "measureTotals"], P_SHAPE + SEG + CAP + CEN + P_FONT),
    "measure_angle": (KIND + LINE + START_AUTO + ["styleHighlight"] + TAIL + FONT
                      + ["Totals:", "measureTotals"], P_LINE + P_ENDS + CAP + P_FONT),
    "measure_radius": (KIND + LINE + START_AUTO + ["styleHighlight"] + TAIL + FONT
                       + ["Totals:", "measureTotals"], P_LINE + P_ENDS + CAP + P_FONT),
    "measure_diameter": (KIND + LINE + START_AUTO + ["styleHighlight"] + TAIL + FONT
                         + ["Totals:", "measureTotals"], P_LINE + P_ENDS + CAP + P_FONT),
    "count": (KIND + ["Line:", "lineColour", "overallOpacity", "lineWidth"] + FILL
              + ["Symbol:", "countSymbol"] + FONT + ["Totals:", "measureTotals"],
              ["Colour:", "Fill Colour:", "Opacity:", "Fill Opacity:", "Line Width:"] + P_FONT),
    # shot 01: … Hatch ▾, highlight, Add a cut-out, Units ▾, Caption ▾, Totals;
    # the panel as the user's photo of Revu's (sketch_rect_panel.jpg)
    "sketch_rect": (KIND + LINE + ["Radius:", "cornerRadius"] + FILL + HATCH
                    + ["styleHighlight", "styleCutout"] + TAIL + ["Totals:", "measureTotals"],
                    P_SHAPE + ["Corner Radius:"] + SEG + CAP + CEN + P_FONT),
    "sketch_ellipse": (KIND + LINE + FILL + HATCH + ["styleHighlight", "styleCutout"] + TAIL
                       + ["Totals:", "measureTotals"], P_SHAPE + CAP + CEN + P_FONT),
}


@pytest.mark.parametrize("tool", list(KINDS))
def test_each_kinds_bar_and_panel_are_revus(window, tool):
    bar, rows = KINDS[tool]
    drawn(window, tool)
    assert bar_widgets(window) == bar, tool
    assert panel_rows(window) == rows, tool


# ---------------------------------------------------------------------------
# the line-end colour (shots 05, 06, 09)
# ---------------------------------------------------------------------------
@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    window.show_panel("dock_properties", True)
    pump()
    return window


def the_line(w):
    from calcforge.items.shapes import PolyItem
    return markups(w, PolyItem)[0]


def draw_line(w, tool="line"):
    w.select_tool(tool)
    drag(w, page(w, 150, 300), page(w, 400, 300))
    w.select_tool("select")
    line = the_line(w)
    select(w, line)
    return line


def colour_picked(w, button, colour: str) -> None:
    """Click the swatch and pick *colour* in Revu's colour picker."""
    from calcforge.ui import colorpicker
    colorpicker.ANSWERS.append(colour)
    assert button.isVisible(), button.objectName()
    QTest.mouseClick(button, Qt.LeftButton)
    pump()


def test_the_line_end_colour_comes_with_a_filled_end(w):
    """Revu shows the swatch once an end is a filled one (shot 02 has none
    on a bare line; shots 05, 06 and 09 have it after a Closed end)."""
    draw_line(w)
    assert not shown_on_bar(w, w.end_fill_button)
    pick(w.arrow_end_combo, "open")
    assert not shown_on_bar(w, w.end_fill_button), "an open end has nothing to fill"
    pick(w.arrow_end_combo, "arrow")
    assert shown_on_bar(w, w.end_fill_button)
    widgets = bar_widgets(w)
    assert widgets.index("lineEndFill") == widgets.index("arrowSize") + 1, \
        "after End's Auto ▾, as Revu's"
    pick(w.arrow_end_combo, "none")
    pick(w.arrow_start_combo, "dot")              # Round, on the start alone
    assert shown_on_bar(w, w.end_fill_button)
    assert w.end_fill_button.color() == the_line(w).style.stroke, \
        "it starts as the line's own colour"


def test_line_end_colour_one_undo_step_drawn_saved_and_read_back(w, tmp_path):
    draw_line(w, "arrow")
    assert the_line(w).style.arrow_end == "arrow"
    stroke = the_line(w).style.stroke
    before = w.undo_stack.index()
    colour_picked(w, w.end_fill_button, "#00a000")
    assert w.undo_stack.index() == before + 1, "one undo step"
    assert the_line(w).style.end_fill == "#00a000"
    assert the_line(w).style.stroke == stroke, "the line keeps its colour"
    w.undo_stack.undo()
    pump()
    assert the_line(w).style.end_fill == ""
    w.undo_stack.redo()
    pump()
    assert the_line(w).style.end_fill == "#00a000"
    # the Properties panel's Fill Colour is the same thing
    select(w, the_line(w))
    from calcforge.ui.widgets import ColorButton
    panel = w.properties_panel.findChild(ColorButton, "lineEndFill")
    assert panel is not None and panel.color() == "#00a000"
    # drawn so: the head green, the shaft the line's colour
    line = the_line(w)
    tip = line.mapToScene(line.points[-1])
    w.view.scene().clearSelection()
    pump()
    shot = w.view.viewport().grab().toImage()
    ratio = shot.devicePixelRatio() or 1.0
    at = w.view.mapFromScene(tip - QPointF(6, 0))
    head = QColor(shot.pixel(int(at.x() * ratio), int(at.y() * ratio)))
    assert head.green() > head.red() + 40 and head.green() > head.blue() + 40, head.name()
    # saved: the Line's /IC, which another reader fills the head with
    path = save_and_reopen(w, tmp_path)
    with pymupdf.open(path) as document:
        (annot,) = [a for a in document[0].annots() if a.type[1] == "Line"]
        fill = annot.colors["fill"]
        assert [round(v, 2) for v in fill] == [0.0, round(160 / 255, 2), 0.0]
        picture = document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), annots=True)
        image = QImage(picture.samples, picture.width, picture.height, picture.stride,
                       QImage.Format_RGB888).copy()
    end = QPointF(400, 300)
    near = QRectF(end.x() * 2 - 26, end.y() * 2 - 10, 22, 20)
    assert ink_in(image, near, lambda c: c.green() > 110 and c.red() < 90) > 0.05, \
        "MuPDF fills the head green too"
    assert the_line(w).style.end_fill == "#00a000", "and it comes back"


def test_no_colour_leaves_the_ends_hollow_and_says_so_in_the_file(w, tmp_path):
    draw_line(w, "arrow")
    colour_picked(w, w.end_fill_button, "")             # No Color
    assert the_line(w).style.end_fill == "none"
    path = save_and_reopen(w, tmp_path)
    with pymupdf.open(path) as document:
        (annot,) = [a for a in document[0].annots() if a.type[1] == "Line"]
        assert not annot.colors["fill"], "no /IC: drawn hollow by every reader"
    assert the_line(w).style.end_fill == "none"


def test_a_line_end_colour_from_another_program_is_read(w, tmp_path):
    path = str(tmp_path / "theirs.pdf")
    document = pymupdf.open()
    sheet = document.new_page()
    annot = sheet.add_line_annot((100, 100), (300, 100))
    annot.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
    annot.set_colors(stroke=(1, 0, 0), fill=(0, 0, 1))
    annot.update()
    plain = sheet.add_line_annot((100, 200), (300, 200))
    plain.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
    plain.set_colors(stroke=(1, 0, 0))
    plain.update()
    document.save(path)
    document.close()
    w.open_from_command_line(path)
    pump()
    from calcforge.items.shapes import PolyItem
    lines = sorted(markups(w, PolyItem), key=lambda i: i.mapToScene(i.points[0]).y())
    assert lines[0].style.end_fill.lower() == "#0000ff"
    assert lines[1].style.end_fill == "none", "no /IC: hollow, as it was written"


def test_line_end_colour_set_as_default_and_kept_in_the_tool_chest(w):
    from calcforge.items.shapes import PolyItem
    from calcforge.ui import toolsets
    draw_line(w, "arrow")
    colour_picked(w, w.end_fill_button, "#0055ff")
    w.set_selected_as_default()
    w.select_tool("arrow")
    drag(w, page(w, 150, 400), page(w, 400, 400))
    w.select_tool("select")
    newest = max(markups(w, PolyItem), key=lambda i: i.mapToScene(i.points[0]).y())
    assert newest.style.end_fill == "#0055ff", "Set as Default"
    stored = toolsets.properties_of(newest)
    again = PolyItem("arrow", [QPointF(0, 0), QPointF(50, 0)])
    toolsets.apply_properties(again, stored)
    assert again.style.end_fill == "#0055ff", "a tool chest tool keeps it"


def test_the_next_arrow_takes_the_bars_line_end_colour(w):
    w.view.scene().clearSelection()
    w.select_tool("arrow")
    pump()
    assert shown_on_bar(w, w.end_fill_button), "the arrow tool's end is Closed"
    colour_picked(w, w.end_fill_button, "#aa00aa")
    drag(w, page(w, 150, 300), page(w, 400, 300))
    w.select_tool("select")
    assert the_line(w).style.end_fill == "#aa00aa"


# ---------------------------------------------------------------------------
# no line ends where Revu has none; the panel's sizes in the bar's words
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tool", ["polygon", "pen", "highlighter", "measure_area",
                                  "measure_perimeter", "measure_volume"])
def test_closed_shapes_and_pens_have_no_line_ends(window, tool):
    drawn(window, tool)
    assert not set(bar_widgets(window)) & {"lineEndStart", "lineEndEnd", "arrowSize",
                                           "arrowStartSize", "lineEndFill"}, tool
    assert not set(panel_rows(window)) & {"Start:", "End:", "Start Size:", "End Size:"}, tool


def test_a_pen_line_that_came_with_a_head_keeps_it_to_change(w):
    from calcforge.items.shapes import PolyItem
    pen = PolyItem("ink", [QPointF(0, 0), QPointF(60, 20), QPointF(120, 0)])
    pen.style.arrow_end = "arrow"
    w.document.pages[0].frame.add_markup(pen, QPointF(200, 300))
    w.view.scene().clearSelection()
    pen.setSelected(True)
    w.refresh_selection()
    pump()
    assert "lineEndEnd" in bar_widgets(w), "never take away what it already has"


def test_the_panels_end_sizes_speak_the_bars_values_both_ways(w):
    draw_line(w, "arrow")
    panel = w.properties_panel.findChild(QComboBox, "arrowSize")
    assert [panel.itemText(i) for i in range(panel.count())][:9] == [
        "Auto", "25%", "50%", "75%", "100%", "125%", "150%", "200%", "400%"]
    assert panel.currentText() == "Auto"
    # the bar's 150% shows in the panel
    pick(w.arrow_size_spin, 1.5)
    panel = w.properties_panel.findChild(QComboBox, "arrowSize")
    assert panel.currentText() == "150%"
    # and the panel's 50% on the bar, as one undo step
    before = w.undo_stack.index()
    pick(panel, 0.5)
    assert w.undo_stack.index() == before + 1
    assert the_line(w).style.arrow_size == pytest.approx(0.5)
    select(w, the_line(w))
    assert w.arrow_size_spin.currentText() == "50%"


# ---------------------------------------------------------------------------
# the lists: pictures alone with a ✓ (shot 10), ✓ on sizes (11–13), names whole
# ---------------------------------------------------------------------------
def _list_picture(combo) -> QImage:
    combo.showPopup()
    pump()
    picture = combo.view().window().grab().toImage()
    return picture


def test_the_end_list_is_pictures_with_a_tick_and_names_as_tooltips(w):
    from calcforge.ui.widgets import CHECK_COLUMN, CheckedListDelegate
    draw_line(w, "arrow")
    combo = w.arrow_end_combo
    delegate = combo.view().itemDelegate()
    assert isinstance(delegate, CheckedListDelegate) and delegate.pictures
    assert combo.findText("Half Arrow") >= 0, "CalcForge's own Half Arrow kept"
    for index in range(combo.count()):
        assert combo.itemData(index, Qt.ToolTipRole) == combo.itemText(index)
    image = _list_picture(combo)
    view = combo.view()
    ratio = image.devicePixelRatio() or 1.0

    def tick_ink(row: int) -> int:
        rect = view.visualRect(view.model().index(row, 0))
        corner = view.viewport().mapTo(view.window(), rect.topLeft())
        return sum(1 for x in range(corner.x() + 2, corner.x() + CHECK_COLUMN - 2)
                   for y in range(corner.y() + 2, corner.y() + rect.height() - 2)
                   if QColor(image.pixel(int(x * ratio), int(y * ratio))).lightness() > 170)
    assert tick_ink(combo.currentIndex()) > 4, "the ✓ on the current end"
    assert tick_ink(0) == 0, "no ✓ on the others"
    # pictures, no words: a row is no wider than its picture needs
    assert view.sizeHintForColumn(0) < 100
    combo.hidePopup()


def test_the_size_and_style_lists_tick_the_current_one_and_cut_no_name_short(w):
    from calcforge.ui.widgets import CheckedListDelegate
    draw_line(w, "arrow")
    assert isinstance(w.arrow_size_spin.view().itemDelegate(), CheckedListDelegate)
    combo = w.dash_combo
    _list_picture(combo)
    view = combo.view()
    metrics = view.fontMetrics()
    index = combo.findText("Long Dash Dot Dot")
    assert index >= 0
    rect = view.visualRect(view.model().index(index, 0))
    assert rect.width() >= metrics.horizontalAdvance("Long Dash Dot Dot") + 150 + 26, \
        "the name whole, the sample beside it"
    combo.hidePopup()


# ---------------------------------------------------------------------------
# a note's Icon ▾ (Revu's: Comment, Help, Insert, Key, New Paragraph, Note,
# Paragraph), on the bar and in the panel
# ---------------------------------------------------------------------------
def the_note(w):
    from calcforge.items.text import NoteItem
    return markups(w, NoteItem)[0]


def test_a_notes_icon_from_the_bar_and_the_panel_saved_as_the_pdfs_name(w, tmp_path):
    from calcforge.items.text import NOTE_ICONS
    w.select_tool("note")
    click(w, page(w, 200, 300))
    key(w, Qt.Key_Escape)
    w.select_tool("select")
    select(w, the_note(w))
    combo = w.note_icon_combo
    assert [combo.itemText(i) for i in range(combo.count())] == [
        words for _key, words in NOTE_ICONS] == [
        "Comment", "Help", "Insert", "Key", "New Paragraph", "Note", "Paragraph"]
    assert combo.currentData() == "Note"
    before = w.undo_stack.index()
    pick(combo, "Key")
    assert w.undo_stack.index() == before + 1, "one undo step"
    assert the_note(w).icon == "Key"
    # drawn differently: a key is not a page of lines
    from tests.test_propbar_gaps import _head_ink  # noqa: F401 - same harness

    def drawn_as(icon):
        note = the_note(w)
        image = QImage(40, 40, QImage.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.translate(10, 10)
        kept = note.icon
        note.icon = icon
        note.paint_visible(painter)
        note.icon = kept
        painter.end()
        return image
    assert drawn_as("Key") != drawn_as("Note")
    w.undo_stack.undo()
    pump()
    assert the_note(w).icon == "Note"
    w.undo_stack.redo()
    pump()
    # the panel has Icon, the same list
    select(w, the_note(w))
    panel = w.properties_panel.findChild(QComboBox, "noteIconPanel")
    assert panel.currentData() == "Key"
    pick(panel, "Help")
    assert the_note(w).icon == "Help"
    select(w, the_note(w))
    assert w.note_icon_combo.currentData() == "Help", "the bar follows the panel"
    path = save_and_reopen(w, tmp_path)
    with pymupdf.open(path) as document:
        (annot,) = [a for a in document[0].annots() if a.type[1] == "Text"]
        assert document.xref_get_key(annot.xref, "Name") == ("name", "/Help")
    assert the_note(w).icon == "Help"


def test_a_notes_colour_and_opacity_on_the_bar(w):
    w.select_tool("note")
    click(w, page(w, 200, 300))
    key(w, Qt.Key_Escape)
    w.select_tool("select")
    select(w, the_note(w))
    colour_picked(w, w.note_colour_button, "#80c0ff")
    assert the_note(w).style.fill == "#80c0ff"
    w.note_opacity_spin.setValue(60)
    pump()
    assert the_note(w).style.opacity == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# Sketch to Scale: shot 01's tail — cut-out, Units ▾, Caption ▾, Totals
# ---------------------------------------------------------------------------
def the_shape(w):
    from calcforge.items.shapes import RectItem
    return markups(w, RectItem)[0]


def draw_sketch(w, tool="sketch_rect"):
    w.select_tool(tool)
    drag(w, page(w, 150, 300), page(w, 330, 420))
    key(w, Qt.Key_Escape)
    w.select_tool("select")
    shape = the_shape(w)
    select(w, shape)
    return shape


def test_sketch_to_scale_totals_say_its_area_or_that_the_scale_is_not_set(w):
    draw_sketch(w)
    assert shown_on_bar(w, w.totals_button)
    assert w.totals_button.currentText() == "Area = Scale Not Set"
    scaled(w, 100)
    shape = the_shape(w)
    shape.refresh(page=w.current_page())
    select(w, shape)
    text = w.totals_button.currentText()
    assert text.startswith("Area = ")
    width = 180 * 100 * 25.4 / 72 / 1000
    height = 120 * 100 * 25.4 / 72 / 1000
    assert float(text.split()[2]) == pytest.approx(width * height, rel=0.02)


def test_sketch_to_scale_units_and_caption_like_a_measurements(w, tmp_path):
    scaled(w, 100)
    draw_sketch(w)
    # Units ▾: its own length unit, as one undo step
    QTest.mouseClick(w.units_button, Qt.LeftButton)
    pump()
    assert w.units_popup.isVisible()
    assert w._units_form.isRowVisible(w.units_area_combo), "a shape's area unit"
    assert not w._units_form.isRowVisible(w.units_volume_combo)
    before = w.undo_stack.index()
    pick(w.units_length_combo, "mm")
    w.units_popup.hide()
    assert w.undo_stack.index() == before + 1
    assert the_shape(w).units == {"length": "mm"}
    assert "mm" in the_shape(w).size_text
    # Caption ▾: shown, with its area beside its size
    select(w, the_shape(w))
    QTest.mouseClick(w.caption_button, Qt.LeftButton)
    pump()
    menu = w.caption_button.popup_menu
    actions = w.caption_part_actions
    assert [p for p, a in actions.items() if a.isVisible()] == [
        "label", "dimensions", "area", "perimeter"]
    assert not w.caption_inline_action.isVisible()
    menu_click(menu, actions["area"])
    menu.hide()
    shape = the_shape(w)
    assert shape.show_size and "A = " in shape.caption_text
    # kept in step with the panel's Show Caption
    select(w, shape)
    assert w.properties_panel.findChild(QCheckBox, "showCaption").isChecked()
    save_and_reopen(w, tmp_path)
    again = the_shape(w)
    assert again.units == {"length": "mm"} and "area" in again.caption_parts


def test_a_cut_out_from_a_sketch_to_scale_shapes_bar(w):
    scaled(w, 100)
    shape = draw_sketch(w)
    whole = shape.area_value().magnitude
    QTest.mouseClick(w.cutout_button, Qt.LeftButton)
    pump()
    assert w.view.tool_key == "cutout_polygon"
    for x, y in ((200, 330), (260, 330), (260, 380), (200, 380)):
        click(w, page(w, x, y))
    key(w, Qt.Key_Return)
    shape = the_shape(w)
    assert len(shape.cutouts) == 1
    assert shape.area_value().magnitude == pytest.approx(
        whole * (1 - 60 * 50 / (180 * 120)), rel=0.03)


# ---------------------------------------------------------------------------
# Highlight: only the inside multiplies, the border stays as it is
# ---------------------------------------------------------------------------
def _page_with_black_words(tmp_path) -> str:
    path = str(tmp_path / "words.pdf")
    document = pymupdf.open()
    sheet = document.new_page()
    sheet.draw_rect(pymupdf.Rect(150, 280, 450, 460), color=(0, 0, 0), fill=(0, 0, 0))
    document.save(path)
    document.close()
    return path


def test_highlight_multiplies_the_inside_and_leaves_the_border_as_it_is(w, tmp_path):
    from calcforge.items.shapes import RectItem
    w.open_from_command_line(_page_with_black_words(tmp_path))
    w.view.set_zoom(1.0)
    pump()
    frame = w.document.pages[0].frame
    shape = RectItem("rect", QRectF(0, 0, 200, 200))
    shape.style.fill, shape.style.fill_opacity = "#ffe066", 1.0
    shape.style.stroke, shape.style.width = "#1060ff", 8.0
    # half over the black block, half over white paper
    frame.add_markup(shape, QPointF(350, 200))
    select(w, shape)

    def looks():
        w.view.scene().clearSelection()
        pump()
        image = frame.render_image(72.0, for_print=True)
        inside_on_black = QColor(image.pixel(380, 380))
        inside_on_white = QColor(image.pixel(500, 380))
        border_on_black = QColor(image.pixel(350, 380))
        return inside_on_black, inside_on_white, border_on_black
    plain = looks()
    assert plain[0].lightness() > 150, "a solid fill covers the black"
    select(w, shape)
    QTest.mouseClick(w.highlight_button, Qt.LeftButton)
    pump()
    shape = markups(w, RectItem)[0]
    assert shape.style.blend == "multiply"
    lit = looks()
    assert lit[0].lightness() < 40, "the black shows through the inside"
    assert lit[1].name() == plain[1].name(), "over paper, the fill as it was"
    assert lit[2].name() == plain[2].name(), "the border not multiplied over the black"
    assert lit[2].blue() > 200
    # saved: other readers see the same — no annotation-level /BM, the
    # inside under a Multiply ExtGState in the appearance
    path = save_and_reopen(w, tmp_path)
    with pymupdf.open(path) as document:
        (annot,) = [a for a in document[0].annots() if a.type[1] == "Square"]
        assert document.xref_get_key(annot.xref, "BM")[0] == "null"
        picture = document[0].get_pixmap(matrix=pymupdf.Matrix(1, 1), annots=True)
        image = QImage(picture.samples, picture.width, picture.height, picture.stride,
                       QImage.Format_RGB888).copy()
    assert QColor(image.pixel(380, 380)).lightness() < 60, "MuPDF: black through the inside"
    border = QColor(image.pixel(350, 380))
    assert border.blue() > 200 and border.red() < 60, border.name()
    assert QColor(image.pixel(500, 380)).name() == plain[1].name()
    assert markups(w, RectItem)[0].style.blend == "multiply", "and it comes back"


def test_the_highlighter_and_a_line_still_multiply_whole(w):
    from calcforge.items.shapes import PolyItem
    pen = PolyItem("highlighter", [QPointF(0, 0), QPointF(100, 0)])
    assert pen.style.blend == "multiply" and not pen.multiplies_inside_only()
    line = PolyItem("line", [QPointF(0, 0), QPointF(100, 0)])
    line.style.blend = "multiply"
    assert not line.multiplies_inside_only()


def test_an_older_files_annotation_level_multiply_still_reads_as_highlight(w, tmp_path):
    path = str(tmp_path / "old.pdf")
    document = pymupdf.open()
    sheet = document.new_page()
    annot = sheet.add_rect_annot(pymupdf.Rect(100, 100, 200, 200))
    annot.set_colors(stroke=(0, 0, 1), fill=(1, 1, 0))
    annot.update()
    document.xref_set_key(annot.xref, "BM", "/Multiply")
    document.save(path)
    document.close()
    w.open_from_command_line(path)
    pump()
    from calcforge.items.shapes import RectItem
    assert markups(w, RectItem)[0].style.blend == "multiply"


# ---------------------------------------------------------------------------
# Show Segment Values, Show Caption + Edit, Show Centroid (the user's photo)
# ---------------------------------------------------------------------------
def tick(box) -> None:
    """Click a tick box (or a radio button) on its box, as a person does."""
    from PySide6.QtCore import QPoint
    assert box.isVisible() and box.isEnabled(), box.objectName()
    QTest.mouseClick(box, Qt.LeftButton, Qt.NoModifier, QPoint(8, box.height() // 2))
    pump()


def panel_tick(w, name):
    box = w.properties_panel.findChild(QAbstractButton, name)
    assert box is not None and box.isVisible(), name
    return box


def _ink_outside(item, colour_test) -> int:
    """Pixels of the given colour drawn round the shape, outside its box."""
    image = QImage(700, 600, QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.translate(200, 200)
    item.paint_visible(painter)
    painter.end()
    box = item.local_rect().normalized().translated(200, 200)
    count = 0
    for y in range(0, 600, 1):
        for x in range(0, 700, 2):
            if box.adjusted(-3, -3, 3, 3).contains(x, y):
                continue
            if colour_test(QColor(image.pixel(x, y))):
                count += 1
    return count


def test_segment_values_written_on_each_side_saved_and_undone(w, tmp_path):
    scaled(w, 100)
    draw_sketch(w)
    the_shape(w).style.text_color = "#00a000"
    show = panel_tick(w, "showSegmentValues")
    along = panel_tick(w, "segmentAlignAlong")
    level = panel_tick(w, "segmentAlignLevel")
    assert along.isChecked() and not along.isEnabled() and not level.isEnabled()

    def green(c):
        return c.green() > 120 and c.red() < 100 and c.blue() < 100
    assert _ink_outside(the_shape(w), green) == 0
    before = w.undo_stack.index()
    tick(show)
    assert w.undo_stack.index() == before + 1
    shape = the_shape(w)
    assert shape.segment_values and len(shape.segment_texts) == 4
    assert shape.segment_texts[0].endswith(" m") and shape.segment_texts[1].endswith(" m")
    written = _ink_outside(shape, green)
    assert written > 40, "each side's length written beside it, in the font colour"
    # Align Horizontally
    select(w, shape)
    tick(panel_tick(w, "segmentAlignLevel"))
    pump()
    assert the_shape(w).segment_align == "horizontal"
    w.undo_stack.undo()
    pump()
    assert the_shape(w).segment_align == "segment"
    w.undo_stack.redo()
    pump()
    path = save_and_reopen(w, tmp_path)
    again = the_shape(w)
    assert again.segment_values and again.segment_align == "horizontal"
    # and in the written PDF's appearance: green words round the shape
    with pymupdf.open(path) as document:
        words = document[0].get_text("words")
        picture = document[0].get_pixmap(matrix=pymupdf.Matrix(1, 1), annots=True)
        image = QImage(picture.samples, picture.width, picture.height, picture.stride,
                       QImage.Format_RGB888).copy()
    left, top = 150, 300
    above = QRectF(left, top - 20, 180, 16)
    assert ink_in(image, above, green) > 0.01, "the top side's length, above it"


def test_show_centroid_marks_the_middle(w, tmp_path):
    scaled(w, 100)
    draw_sketch(w)
    shape = the_shape(w)
    shape.style.stroke = "#ff0000"
    shape.style.fill = ""
    select(w, shape)
    before = w.undo_stack.index()
    tick(panel_tick(w, "showCentroid"))
    pump()
    assert w.undo_stack.index() == before + 1
    shape = the_shape(w)
    centre = shape.centroid_point()
    box = shape.local_rect().normalized()
    assert centre.x() == pytest.approx(box.center().x(), abs=0.5)
    assert centre.y() == pytest.approx(box.center().y(), abs=0.5)
    image = QImage(int(box.right()) + 20, int(box.bottom()) + 20, QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    shape.paint_visible(painter)
    painter.end()
    middle = QColor(image.pixel(int(centre.x()), int(centre.y())))
    assert middle.red() > 150 and middle.green() < 120, "a cross through the centroid"
    save_and_reopen(w, tmp_path)
    assert the_shape(w).show_centroid


def test_an_areas_centroid_and_segments_and_its_caption_tick(w):
    from calcforge.items.measure import MeasureItem
    from tests.test_propbar_gaps import draw_area
    scaled(w, 100)
    area = draw_area(w)
    select(w, area)
    tick(panel_tick(w, "showSegmentValues"))
    tick(panel_tick(w, "showCentroid"))
    area = markups(w, MeasureItem)[0]
    assert area.segment_values and area.show_centroid and len(area.segment_texts) == 4
    # Show Caption is the bar's Caption ▾ ▸ Show Caption
    select(w, area)
    caption = panel_tick(w, "showCaption")
    assert caption.isChecked()
    tick(caption)
    area = markups(w, MeasureItem)[0]
    assert not area.show_label
    select(w, area)
    QTest.mouseClick(w.caption_button, Qt.LeftButton)
    pump()
    assert not w.caption_show_action.isChecked(), "the bar's Caption ▾ in step"
    w.caption_button.popup_menu.hide()


def test_edit_caption_picks_its_values_and_a_label(w):
    from calcforge.items.measure import MeasureItem
    from tests.test_propbar_gaps import draw_area
    scaled(w, 100)
    area = draw_area(w)
    select(w, area)
    QTest.mouseClick(panel_tick(w, "editCaption"), Qt.LeftButton)
    pump()
    dialog = w.properties_panel.caption_dialog
    assert dialog.isVisible()
    perimeter = dialog.findChild(QCheckBox, "captionPart_perimeter")
    label = dialog.findChild(QCheckBox, "captionPart_label")
    tick(perimeter)
    tick(label)
    words = dialog.findChild(QWidget, "captionLabel")
    words.setFocus()
    QTest.keyClicks(words, "Slab A")
    before = w.undo_stack.index()
    QTest.keyClick(words, Qt.Key_Return)
    pump()
    assert w.undo_stack.index() == before + 1, "one undo step"
    area = markups(w, MeasureItem)[0]
    lines = area.value_text.split("\n")
    assert lines[0] == "Slab A" and lines[1].startswith("A = ") and lines[2].startswith("P = ")


def test_the_new_rows_set_a_markup_styles_look(w):
    """With a tool in hand and a markup style held, the panel's rows set
    that style — as every other row does."""
    from calcforge.ui import markupstyles
    w.view.scene().clearSelection()
    w.select_tool("sketch_rect")
    pump()
    styles = w.markup_styles
    QTest.mouseClick(styles.bar.add_button, Qt.LeftButton)       # Revu's +
    pump()
    assert styles.editing() == 1
    w.properties_panel.show_items([])
    pump()
    tick(panel_tick(w, "showCentroid"))
    tick(panel_tick(w, "showSegmentValues"))
    pump()
    stored = markupstyles.styles_for("sketch_rect")[0].payload
    assert stored.get("show_centroid") and stored.get("segment_values")
    drag(w, page(w, 150, 300), page(w, 330, 420))
    key(w, Qt.Key_Escape)
    w.select_tool("select")
    assert the_shape(w).show_centroid and the_shape(w).segment_values, \
        "the next one drawn in that style has them"


def test_segment_values_and_centroid_set_as_default(w):
    scaled(w, 100)
    draw_sketch(w)
    tick(panel_tick(w, "showSegmentValues"))
    tick(panel_tick(w, "showCentroid"))
    shape = the_shape(w)
    select(w, shape)
    w.set_selected_as_default()
    from calcforge.items.shapes import RectItem
    w.select_tool("sketch_rect")
    drag(w, page(w, 150, 500), page(w, 300, 600))
    key(w, Qt.Key_Escape)
    w.select_tool("select")
    newest = max(markups(w, RectItem), key=lambda i: i.mapToScene(i.local_rect().topLeft()).y())
    assert newest.segment_values and newest.show_centroid
    from calcforge.ui import toolsets
    again = RectItem("rect", QRectF(0, 0, 50, 50), to_scale=True)
    toolsets.apply_properties(again, toolsets.properties_of(newest))
    assert again.segment_values and again.show_centroid, "a tool chest tool keeps them"
