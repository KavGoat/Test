"""The Markups List as Revu's (the user, 2026-10-19: "Markups list does not
allow editing text inside it, filtering and sorting icons overlap and does
not look the same as bluebeam").

Revu 21's manual: the cells of the editable columns are edited in place —
click a picked row's cell (or double-click, or F2), type, Enter keeps it and
Esc leaves it. Editing Comments changes a text box's or callout's words.
The read-only columns (Page, Type, Date, measured values) do not edit. Each
heading has its title, the sort arrow next to it and the filter button at
its right edge, never on top of each other.

Driven as a person drives it: clicks and double-clicks on the cells where
they are drawn, keys typed into the box, Ctrl+Z for undo.
"""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QLineEdit

from calcforge.items.measure import CountItem
from calcforge.items.shapes import RectItem
from calcforge.items.text import CalloutItem, TextItem


def pump(seconds=0.0):
    end = time.monotonic() + seconds
    while True:
        for _ in range(4):
            QApplication.processEvents()
        if time.monotonic() >= end:
            break
        time.sleep(0.005)


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.show_markups_list(True)
    pump()
    yield window


def add(window, item, at=(100, 100)):
    window.document.pages[0].frame.add_markup(item, QPointF(*at))
    window.refresh_lists()
    pump()
    return item


def a_rect(window, subject="Wall", at=(100, 100)):
    item = RectItem("rect", QRectF(0, 0, 80, 40))
    item.subject = subject
    return add(window, item, at)


def markup(window, uid):
    """The markup now (undo makes markups afresh: never keep one)."""
    for item in window.document.pages[0].frame.ordered_markups():
        if item.uid == uid:
            return item
    return None


def node_of(panel, uid):
    tree = panel.tree
    for top in range(tree.topLevelItemCount()):
        parent = tree.topLevelItem(top)
        for node in [parent] + [parent.child(c) for c in range(parent.childCount())]:
            data = node.data(0, Qt.UserRole)
            if data and data[1] == uid:
                return node
    raise AssertionError(f"no row for {uid}")


def cell_point(panel, uid, column_name):
    """Where the cell is drawn, on the list's viewport."""
    tree = panel.tree
    column = panel.COLUMNS.index(column_name)
    tree.scrollToItem(node_of(panel, uid))
    tree.horizontalScrollBar().setValue(0)
    header = tree.header()
    x = header.sectionViewportPosition(column)
    if x < 0 or x + header.sectionSize(column) > tree.viewport().width():
        tree.horizontalScrollBar().setValue(header.sectionPosition(column))
        pump()
    rect = tree.visualItemRect(node_of(panel, uid))
    x = header.sectionViewportPosition(column) + header.sectionSize(column) // 2
    return QRect(x, rect.top(), 1, rect.height()).center()


def double_click_cell(panel, uid, column_name):
    at = cell_point(panel, uid, column_name)
    QTest.mouseClick(panel.tree.viewport(), Qt.LeftButton, Qt.NoModifier, at)
    pump()
    QTest.mouseDClick(panel.tree.viewport(), Qt.LeftButton, Qt.NoModifier, at)
    pump()


def editor_of(panel):
    found = [box for box in panel.tree.viewport().findChildren(QLineEdit)
             if box.objectName() == "markupCellEditor" and box.isVisible()]
    return found[0] if found else None


def type_over(panel, text):
    box = editor_of(panel)
    assert box is not None, "no box opened in the cell"
    assert box.hasFocus()
    QTest.keyClick(box, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(box, text)
    pump()
    return box


def enter(panel):
    QTest.keyClick(editor_of(panel), Qt.Key_Return)
    pump(0.05)


def undo(window):
    QTest.keyClick(window.markups_panel.tree, Qt.Key_Z, Qt.ControlModifier)
    pump()


# -- editing in place ---------------------------------------------------------
def test_double_click_a_subject_type_enter_and_one_undo(win):
    uid = a_rect(win, "Wall").uid
    panel = win.markups_panel
    steps = win.undo_stack.count()
    double_click_cell(panel, uid, "Subject")
    box = type_over(panel, "Slab edge")
    assert box.text() == "Slab edge"
    enter(panel)
    assert editor_of(panel) is None
    assert markup(win, uid).subject == "Slab edge"
    assert node_of(panel, uid).text(panel.COLUMNS.index("Subject")) == "Slab edge"
    assert win.undo_stack.count() == steps + 1, "one step"
    undo(win)
    assert markup(win, uid).subject == "Wall"
    assert node_of(panel, uid).text(panel.COLUMNS.index("Subject")) == "Wall"


def test_f2_edits_the_label_with_the_keyboard(win):
    uid = a_rect(win, "Wall").uid
    panel = win.markups_panel
    tree = panel.tree
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     cell_point(panel, uid, "Label"))
    pump()
    assert tree.currentIndex().column() == panel.COLUMNS.index("Label")
    QTest.keyClick(tree, Qt.Key_F2)
    pump()
    type_over(panel, "W1")
    enter(panel)
    item = markup(win, uid)
    assert item.label == "W1"
    row = node_of(panel, uid)
    assert row.text(panel.COLUMNS.index("Label")) == "W1"
    assert row.text(panel.COLUMNS.index("Type")) == "Rectangle", "Type is the kind, as Revu's"
    undo(win)
    assert markup(win, uid).label == ""


def test_escape_leaves_the_cell_as_it_was(win):
    uid = a_rect(win, "Wall").uid
    panel = win.markups_panel
    steps = win.undo_stack.count()
    double_click_cell(panel, uid, "Author")
    type_over(panel, "Somebody else")
    QTest.keyClick(editor_of(panel), Qt.Key_Escape)
    pump(0.05)
    assert editor_of(panel) is None
    assert markup(win, uid).author != "Somebody else"
    assert win.undo_stack.count() == steps


def test_author_by_keyboard(win):
    uid = a_rect(win, "Wall").uid
    panel = win.markups_panel
    QTest.mouseClick(panel.tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     cell_point(panel, uid, "Author"))
    pump()
    QTest.keyClick(panel.tree, Qt.Key_F2)
    pump()
    type_over(panel, "K. Ithpula")
    enter(panel)
    assert markup(win, uid).author == "K. Ithpula"
    undo(win)
    assert markup(win, uid).author != "K. Ithpula"


def test_comments_shows_and_edits_a_text_boxs_words(win):
    box_item = add(win, TextItem("Check the beam", QRectF(0, 0, 160, 40)), (100, 300))
    uid = box_item.uid
    panel = win.markups_panel
    comment = panel.COLUMNS.index("Comment")
    assert node_of(panel, uid).text(comment) == "Check the beam"
    # a click picks the row, a second click on the picked row's cell edits
    at = cell_point(panel, uid, "Comment")
    QTest.mouseClick(panel.tree.viewport(), Qt.LeftButton, Qt.NoModifier, at)
    pump(QApplication.doubleClickInterval() / 1000 + 0.05)
    QTest.mouseClick(panel.tree.viewport(), Qt.LeftButton, Qt.NoModifier, at)
    pump(QApplication.doubleClickInterval() / 1000 + 0.1)
    box = editor_of(panel)
    assert box is not None and box.text() == "Check the beam"
    type_over(panel, "Check the steel beam")
    enter(panel)
    item = markup(win, uid)
    assert item.text() == "Check the steel beam"
    assert item.comment == "", "the words changed, not a separate comment"
    assert node_of(panel, uid).text(comment) == "Check the steel beam"
    undo(win)
    assert markup(win, uid).text() == "Check the beam"


def test_editing_words_keeps_their_other_line_breaks(win):
    uid = add(win, CalloutItem("First line\nSecond line"), (100, 300)).uid
    panel = win.markups_panel
    double_click_cell(panel, uid, "Comment")
    box = editor_of(panel)
    assert box.text() == "First line Second line"
    box.setCursorPosition(len("First line Second"))
    QTest.keyClicks(box, " long")
    enter(panel)
    assert markup(win, uid).text() == "First line\nSecond long line"


def test_a_notes_comment_is_edited(win):
    from calcforge.items.text import NoteItem
    uid = add(win, NoteItem("Old note"), (300, 300)).uid
    panel = win.markups_panel
    double_click_cell(panel, uid, "Comment")
    type_over(panel, "New note")
    enter(panel)
    assert markup(win, uid).comment == "New note"


def test_typing_in_the_cell_fires_no_shortcut(win):
    uid = a_rect(win, "Wall").uid
    panel = win.markups_panel
    double_click_cell(panel, uid, "Subject")
    box = editor_of(panel)
    QTest.keyClick(box, Qt.Key_End)
    QTest.keyClicks(box, " vdx")                    # V is Select, Delete deletes
    QTest.keyClick(box, Qt.Key_Delete)
    enter(panel)
    assert markup(win, uid) is not None
    assert markup(win, uid).subject == "Wall vdx"


@pytest.mark.parametrize("column", ["Page", "Type", "Colour", "Width", "Value", "Date"])
def test_read_only_columns_refuse(win, column):
    uid = a_rect(win, "Wall").uid
    panel = win.markups_panel
    before = markup(win, uid).serialize()
    steps = win.undo_stack.count()
    double_click_cell(panel, uid, column)
    assert editor_of(panel) is None
    assert panel.tree.state() != QAbstractItemView.EditingState
    QTest.keyClick(panel.tree, Qt.Key_F2)
    pump()
    assert editor_of(panel) is None
    assert markup(win, uid).serialize() == before
    assert win.undo_stack.count() == steps


def test_a_counts_value_is_read_only_but_its_subject_edits(win):
    count = add(win, CountItem(), (200, 200))
    panel = win.markups_panel
    double_click_cell(panel, count.uid, "Value")
    assert editor_of(panel) is None
    double_click_cell(panel, count.uid, "Subject")
    type_over(panel, "Bolts")
    enter(panel)
    assert markup(win, count.uid).subject == "Bolts"


def test_a_group_heading_does_not_edit(win):
    a_rect(win, "Wall")
    panel = win.markups_panel
    tree = panel.tree
    heading = tree.topLevelItem(0)
    rect = tree.visualItemRect(heading)
    at = rect.center()
    at.setX(tree.header().sectionViewportPosition(panel.COLUMNS.index("Subject")) + 10)
    QTest.mouseDClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, at)
    pump()
    assert editor_of(panel) is None


# -- the headings -------------------------------------------------------------
def _no_overlap(header, column):
    section = header.section_rect(column)
    text, arrow, button = header.parts(column)
    shown = [r for r in (text, arrow, button) if r.isValid() and not r.isEmpty()]
    for one in shown:
        assert section.contains(one), (column, section, one)
    for i, one in enumerate(shown):
        for other in shown[i + 1:]:
            assert not one.intersects(other), (header.sectionSize(column), text, arrow, button)
    return text, arrow, button


@pytest.mark.parametrize("points", [9, 12, 15])
def test_title_sort_arrow_and_filter_never_overlap(win, points):
    panel = win.markups_panel
    header = panel.tree.header()
    font = QFont(header.font())
    font.setPointSize(points)                # as a bigger display scale would draw it
    header.setFont(font)
    panel.set_filter_list(True)
    subject = panel.COLUMNS.index("Subject")
    a_rect(win, "Alpha")
    panel.tree.sortByColumn(subject, Qt.DescendingOrder)
    panel.set_column_filter(subject, {"Alpha"})
    pump()
    assert header.isSortIndicatorShown() and header.sortIndicatorSection() == subject
    for width in range(header.minimumSectionSize(), 320, 3):
        header.resizeSection(subject, width)
        text, arrow, button = _no_overlap(header, subject)
        assert button.isValid(), "the filter button is always there"
        assert arrow.isValid(), "and the sort arrow"
        if width >= header.sectionSizeFromContents(subject).width():
            assert text.width() >= header.fontMetrics().horizontalAdvance("Subject") - 1, \
                "wide enough: the whole title"
    # Filter List off: no button, and the title and arrow still apart
    panel.set_filter_list(False)
    for width in range(header.minimumSectionSize(), 200, 7):
        header.resizeSection(subject, width)
        text, arrow, button = _no_overlap(header, subject)
        assert not button.isValid()
    panel.set_filter_list(True)


def test_the_arrow_sits_after_the_title_and_the_button_at_the_right_edge(win):
    panel = win.markups_panel
    header = panel.tree.header()
    panel.set_filter_list(True)
    column = panel.COLUMNS.index("Type")
    panel.tree.sortByColumn(column, Qt.AscendingOrder)
    header.resizeSection(column, 160)
    pump()
    section = header.section_rect(column)
    text, arrow, button = header.parts(column)
    assert text.left() - section.left() < 10, "the title on the left, as Revu's"
    assert 0 < arrow.left() - text.right() < 10, "the arrow just after the title"
    assert section.right() - button.right() < 6, "the button at the right edge"
    # a click on the title still sorts, a click on the button filters only
    order = header.sortIndicatorOrder()
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier, text.center())
    pump()
    assert header.sortIndicatorOrder() != order


def test_the_headings_are_drawn_without_qts_own_arrow(win):
    """Nothing is drawn in the gap between the title's arrow and the
    button: Qt's own sort arrow used to sit under the funnel."""
    panel = win.markups_panel
    header = panel.tree.header()
    panel.set_filter_list(True)
    column = panel.COLUMNS.index("Subject")
    panel.tree.sortByColumn(column, Qt.DescendingOrder)
    header.resizeSection(column, 220)
    pump()
    image = header.viewport().grab().toImage()
    ratio = image.devicePixelRatio()
    text, arrow, button = header.parts(column)
    tall = header.viewport().height()
    y0, y1 = tall // 4, tall * 3 // 4
    background = image.pixelColor(int((arrow.right() + 6) * ratio), int(y0 * ratio))
    for x in range(arrow.right() + 3, button.left() - 2):
        for y in range(y0, y1):
            colour = image.pixelColor(int(x * ratio), int(y * ratio))
            assert abs(colour.lightness() - background.lightness()) < 30, (x, y)
