"""Revu's Page Setup, driven the way a person drives it (the user's
decision, 2026-10-15: "Page Setup follows Revu's layout and really resizes
the content (Auto Scale, Scale, Offset, Rotation, Center, Fit to Media), with
a preview and a Pages range").

Every test opens the dialog from the real Document menu (or a page's own
menu) with the mouse, sets its fields with the mouse and the keyboard, and
OKs it. Each option is checked for what it does to the page's size, to where
a known markup lands, to a measurement's value, to the saved file as another
reader renders it, and to undo and redo.
"""
import math

import pymupdf
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMenu

from calcforge.core.document import MM_TO_PT, PageScale
from calcforge.items.measure import MeasureItem
from calcforge.ui.pagesetup import PageSetupDialog
from tests.test_usability import drag, on_page

A4_WIDE = (842.0, 595.0)
A3_WIDE = (420 * MM_TO_PT, 297 * MM_TO_PT)
RED = (100, 100, 300, 200)                # the drawing's red block, on every page


def settle(times=4):
    for _ in range(times):
        QApplication.processEvents()


def _drawing(path, pages=3):
    made = pymupdf.open()
    for number in range(pages):
        page = made.new_page(width=A4_WIDE[0], height=A4_WIDE[1])
        page.draw_rect(pymupdf.Rect(*RED), color=(1, 0, 0), fill=(1, 0, 0))
        page.insert_text((60, 560), f"Sheet {number + 1}", fontsize=18)
    made.save(str(path))
    made.close()


@pytest.fixture
def drawn(window, tmp_path):
    """A shown window with a three-page A4 landscape drawing at 1:100, a
    measurement and a cloud drawn on page 1 with the mouse."""
    path = tmp_path / "drawing.pdf"
    _drawing(path)
    window.show()
    window.activateWindow()
    window.open_from_command_line(str(path))
    window.set_page_scale(PageScale.from_ratio(100), [0, 1, 2])
    window.go_to_page(0)
    window.view.set_zoom(1.0)
    window.view.go_to_page_top(0)
    settle()
    window.select_tool("measure_length")
    drag(window.view, *on_page(window, 0, 100, 250), *on_page(window, 0, 300, 250))
    window.select_tool("cloud")
    drag(window.view, *on_page(window, 0, 400, 300), *on_page(window, 0, 500, 400))
    window.select_tool("select")
    window.scene.clearSelection()
    window.undo_stack.clear()
    window.document.path = str(tmp_path / "saved.pdf")
    return window


def measure(window, index=0):
    return next(i for i in window.document.pages[index].frame.markups()
                if isinstance(i, MeasureItem))


def cloud(window, index=0):
    return next(i for i in window.document.pages[index].frame.markups()
                if getattr(i, "kind", "") == "cloud")


def centre_of(item):
    return item.mapToParent(item.local_rect().center())


def size_of(window, index=0):
    page = window.document.pages[index]
    return page.width_pt, page.height_pt


# ---------------------------------------------------------------------------
# driving the dialog
# ---------------------------------------------------------------------------

def when_modal(kind, then, failures):
    """Run *then* on the modal *kind* once it is up (a dialog's exec waits)."""
    def look():
        widget = QApplication.activeModalWidget()
        if isinstance(widget, kind) and widget.isVisible():
            try:
                widget.activateWindow()
                settle()
                then(widget)
            except BaseException as exc:          # noqa: BLE001
                failures.append(exc)
                widget.reject()
            return
        QTimer.singleShot(10, look)
    QTimer.singleShot(0, look)


def when_popup(then, failures):
    def look():
        widget = QApplication.activePopupWidget()
        if isinstance(widget, QMenu) and widget.isVisible():
            try:
                then(widget)
            except BaseException as exc:          # noqa: BLE001
                failures.append(exc)
                widget.close()
            return
        QTimer.singleShot(10, look)
    QTimer.singleShot(0, look)


def from_document_menu(window):
    """Document ▸ Page Setup…, with the mouse on the real menu bar."""
    bar = window.menuBar()
    entry = next(a for a in bar.actions() if a.text().replace("&", "") == "Document")
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.actionGeometry(entry).center())
    menu = entry.menu()
    settle()
    assert menu.isVisible()
    item = next(a for a in menu.actions() if a.text() == "Page Setup…")
    QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, menu.actionGeometry(item).center())


def page_setup(window, steps, opener=from_document_menu, ok=True):
    """Open Page Setup, do *steps* to it, and OK it with the mouse (or press
    Enter with *ok* "key", or Cancel with False). Says what the dialog said."""
    failures, seen = [], {}

    def drive(dialog):
        steps(dialog)
        settle()
        seen["plan"] = dialog.plan()
        seen["scale"] = dialog.scale_value.text()
        seen["media"] = dialog.media_value.text()
        if ok == "key":
            dialog.buttons.button(QDialogButtonBox.Ok).setFocus()
            QTest.keyClick(dialog, Qt.Key_Return)
        elif ok:
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.Ok), Qt.LeftButton)
        else:
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.Cancel), Qt.LeftButton)
    when_modal(PageSetupDialog, drive, failures)
    opener(window)
    settle()
    window.activateWindow()            # the window has the keyboard again
    settle()
    if failures:
        raise failures[0]
    return seen


def pick(combo, text, shown=True):
    """Open a dropdown with the mouse and click one of its entries (an
    editable one opens from its arrow)."""
    where = QPoint(combo.width() - 8, combo.height() // 2) if combo.isEditable() \
        else combo.rect().center()
    QTest.mouseClick(combo, Qt.LeftButton, Qt.NoModifier, where)
    # a popup ignores a release within a double-click of opening (Qt)
    QTest.qWait(QApplication.doubleClickInterval() + 60)
    view = combo.view()
    assert view.isVisible()
    row = combo.findText(text)
    assert row >= 0, text
    rect = view.visualRect(combo.model().index(row, 0))
    QTest.mouseMove(view.viewport(), rect.center())
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center(), 30)
    settle()
    if shown:                      # the zoom box then shows the zoom it came to
        assert combo.currentText() == text


def type_into(spin, text):
    """Click into a box, select what is there and type over it, then Tab."""
    QTest.mouseClick(spin.lineEdit(), Qt.LeftButton)
    assert spin.hasFocus()
    QTest.keyClick(spin.lineEdit(), Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(spin.lineEdit(), text)
    QTest.keyClick(spin.lineEdit(), Qt.Key_Tab)
    settle(2)


def click(widget):
    QTest.mouseClick(widget, Qt.LeftButton)
    settle(2)


def saved_page(window, index=0):
    """Save with Ctrl+S, and the page as another reader opens it."""
    window.activateWindow()
    settle()
    QTest.keyClick(window.view, Qt.Key_S, Qt.ControlModifier)
    settle()
    document = pymupdf.open(window.document.path)
    return document, document[index]


def red_at(page, x, y):
    """Whether the saved page renders red at x, y (points)."""
    picture = page.get_pixmap(dpi=72, clip=pymupdf.Rect(x - 1, y - 1, x + 1, y + 1))
    r, g, b = picture.pixel(0, 0)[:3]
    return r > 200 and g < 80 and b < 80


def undo_redo_round_trip(window, before, after):
    """Ctrl+Z puts *before* back exactly, Ctrl+Y *after* (state functions)."""
    window.activateWindow()
    settle()
    QTest.keyClick(window.view, Qt.Key_Z, Qt.ControlModifier)
    settle()
    assert state(window) == before
    QTest.keyClick(window.view, Qt.Key_Y, Qt.ControlModifier)
    settle()
    assert state(window) == after


def state(window):
    """Every page as written out, with the bookmarks: what undo must restore."""
    pages = []
    for page in window.document.pages:
        entry = page.to_dict()
        entry["items"] = sorted(
            (round(i.get("x", 0), 3), round(i.get("y", 0), 3), i.get("type"),
             round(i.get("rotation", 0), 3), tuple(round(v, 4) for v in i.get("transform", ())))
            for i in entry["items"])
        pages.append(entry)
    return pages, [m.to_dict() for m in window.document.bookmarks]


# ---------------------------------------------------------------------------
# Media Size, Auto Scale
# ---------------------------------------------------------------------------

def test_a3_with_auto_scale_scales_everything_onto_the_paper(drawn):
    w = drawn
    value = measure(w).value_text
    where = centre_of(cloud(w))
    before = state(w)
    seen = page_setup(w, lambda d: pick(d.media, "A3"))
    factor = min(A3_WIDE[0] / A4_WIDE[0], A3_WIDE[1] / A4_WIDE[1])
    assert seen["scale"] == f"{factor * 100:.2f}%"
    assert size_of(w) == pytest.approx(A3_WIDE, abs=0.01)
    assert size_of(w, 1) == pytest.approx(A4_WIDE, abs=0.01)       # only Current
    dy = (A3_WIDE[1] - A4_WIDE[1] * factor) / 2
    expected = QPointF(where.x() * factor, where.y() * factor + dy)
    landed = centre_of(cloud(w))
    assert landed.x() == pytest.approx(expected.x(), abs=0.05)
    assert landed.y() == pytest.approx(expected.y(), abs=0.05)
    # the measurement measures what it did: the page's scale went with it
    assert measure(w).value_text == value
    assert w.document.pages[0].scale.label == f"1:{100 / factor:.6g}"
    after = state(w)
    document, page = saved_page(w)
    assert page.rect.width == pytest.approx(A3_WIDE[0], abs=0.1)
    middle = (200 * factor, 150 * factor + dy)
    assert red_at(page, *middle)
    assert red_at(page, 100 * factor + 3, 100 * factor + dy + 3)
    assert not red_at(page, 100 * factor - 3, 100 * factor + dy - 3)
    # the cloud went with the drawing: an annotation round its new place
    middle_of = [((a.rect.x0 + a.rect.x1) / 2, (a.rect.y0 + a.rect.y1) / 2)
                 for a in page.annots()]
    assert any(abs(x - expected.x()) < 2 and abs(y - expected.y()) < 2
               for x, y in middle_of), middle_of
    document.close()
    undo_redo_round_trip(w, before, after)
    assert size_of(w) == pytest.approx(A3_WIDE, abs=0.01)


def test_ok_by_the_keyboard_and_cancel_change_nothing_until_asked(drawn):
    w = drawn
    page_setup(w, lambda d: pick(d.media, "A3"), ok=False)
    assert size_of(w) == pytest.approx(A4_WIDE, abs=0.01)
    assert w.undo_stack.count() == 0
    page_setup(w, lambda d: pick(d.media, "A3"), ok="key")
    assert size_of(w) == pytest.approx(A3_WIDE, abs=0.01)
    assert w.undo_stack.count() == 1


def test_custom_page_size_and_portrait(drawn):
    w = drawn

    def steps(d):
        pick(d.media, "Custom Page Size")
        assert d.width_box.isEnabled() and d.height_box.isEnabled()
        type_into(d.width_box, "300")
        type_into(d.height_box, "500")
        assert d.portrait.isChecked()
        click(d.auto_scale)                 # off: the drawing stays its size
        assert not d.auto_scale.isChecked()
        click(d.clear_button)
    page_setup(w, steps)
    page = w.document.pages[0]
    assert (page.width_pt, page.height_pt) == pytest.approx((300 * MM_TO_PT, 500 * MM_TO_PT),
                                                            abs=0.01)
    assert page.setup.orientation == "portrait"
    # 100 %, no offset: the cloud is where it was
    assert centre_of(cloud(w)).x() == pytest.approx(450, abs=0.6)


def test_landscape_swaps_a_standard_size(drawn):
    w = drawn

    def steps(d):
        pick(d.media, "A2")
        click(d.portrait)
        assert d.width_box.value() < d.height_box.value()
        click(d.landscape)
        assert d.width_box.value() == pytest.approx(594.0)
    page_setup(w, steps)
    assert size_of(w) == pytest.approx((594 * MM_TO_PT, 420 * MM_TO_PT), abs=0.01)
    assert w.document.pages[0].setup.size_name == "A2"


# ---------------------------------------------------------------------------
# Scale, Offset
# ---------------------------------------------------------------------------

def test_scale_and_offset_typed_in(drawn):
    w = drawn
    value = measure(w).value_text
    where = centre_of(cloud(w))
    before = state(w)

    def steps(d):
        type_into(d.scale_box, "50")
        assert not d.auto_scale.isChecked()          # a typed scale is not Auto
        type_into(d.offset_x, "20")
        type_into(d.offset_y, "10")
        assert d.scale_value.text() == "50.00%"
    page_setup(w, steps)
    assert size_of(w) == pytest.approx(A4_WIDE, abs=0.01)           # same paper
    x0, y0 = 20 * MM_TO_PT, 10 * MM_TO_PT
    landed = centre_of(cloud(w))
    assert landed.x() == pytest.approx(x0 + where.x() * 0.5, abs=0.05)
    assert landed.y() == pytest.approx(y0 + where.y() * 0.5, abs=0.05)
    assert measure(w).value_text == value
    assert w.document.pages[0].scale.label == "1:200"
    after = state(w)
    document, page = saved_page(w)
    assert red_at(page, x0 + 100, y0 + 75)              # the block's middle, halved
    assert not red_at(page, 280, 180)                   # where its corner was
    document.close()
    undo_redo_round_trip(w, before, after)


def test_centre_puts_the_drawing_in_the_middle(drawn):
    w = drawn

    def steps(d):
        type_into(d.scale_box, "50")
        click(d.centre_button)
        assert d.offset_x.value() == pytest.approx(A4_WIDE[0] / 4 / MM_TO_PT, abs=0.06)
        assert d.offset_y.value() == pytest.approx(A4_WIDE[1] / 4 / MM_TO_PT, abs=0.06)
    page_setup(w, steps)
    where = centre_of(cloud(w))
    assert where.x() == pytest.approx(A4_WIDE[0] / 4 + 450 * 0.5, abs=0.6)
    document, page = saved_page(w)
    assert red_at(page, A4_WIDE[0] / 4 + 100, A4_WIDE[1] / 4 + 75)
    document.close()


# ---------------------------------------------------------------------------
# Rotation, Get Line
# ---------------------------------------------------------------------------

def test_rotation_turns_the_drawing_and_its_markups(drawn):
    w = drawn
    value = measure(w).value_text
    before = state(w)

    def steps(d):
        type_into(d.rotation, "90")
    page_setup(w, steps)
    # a landscape drawing turned a quarter turn, fitted (Auto Scale) onto
    # the same landscape paper
    factor = A4_WIDE[1] / A4_WIDE[0]
    assert size_of(w) == pytest.approx(A4_WIDE, abs=0.01)
    left = (A4_WIDE[0] - A4_WIDE[1] * factor) / 2
    # anticlockwise: a point at (x, y) lands at (y, width - x), scaled
    expected = QPointF(left + 350 * factor, (A4_WIDE[0] - 450) * factor)
    landed = centre_of(cloud(w))
    assert landed.x() == pytest.approx(expected.x(), abs=0.6)
    assert landed.y() == pytest.approx(expected.y(), abs=0.6)
    assert measure(w).value_text == value
    item = measure(w)
    ends = [item.mapToParent(p) for p in (item.points[0], item.points[-1])]
    assert abs(ends[0].x() - ends[1].x()) < 0.01                 # now upright
    after = state(w)
    document, page = saved_page(w)
    assert red_at(page, left + 150 * factor, (A4_WIDE[0] - 200) * factor)
    document.close()
    undo_redo_round_trip(w, before, after)


def test_get_line_sets_the_rotation_from_a_dragged_line(drawn):
    w = drawn
    failures = []
    angle = 12.0

    def first(dialog):
        click(dialog.get_line)                          # closes: drag a line now
    when_modal(PageSetupDialog, first, failures)
    from_document_menu(w)
    settle()
    assert w.view.tool_key == "calibrate"
    seen = {}

    def second(dialog):
        seen["rotation"] = dialog.rotation.value()
        QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.Ok), Qt.LeftButton)
    when_modal(PageSetupDialog, second, failures)
    dx = 300.0
    dy = dx * math.tan(math.radians(angle))
    drag(w.view, *on_page(w, 0, 450, 450), *on_page(w, 0, 450 + dx, 450 + dy))
    settle(10)
    assert not failures, failures
    assert seen["rotation"] == pytest.approx(angle, abs=0.3)
    assert w.view.tool_key == "select"
    assert w.undo_stack.count() == 1
    # the cloud's edges turned the same way as the line went level
    assert cloud(w).rotation() == pytest.approx(-angle, abs=0.3)


def test_escape_in_get_line_brings_the_dialog_back_unchanged(drawn):
    w = drawn
    failures, seen = [], {}

    def first(dialog):
        type_into(dialog.scale_box, "80")
        click(dialog.get_line)
    when_modal(PageSetupDialog, first, failures)
    from_document_menu(w)
    settle()

    def second(dialog):
        seen["scale"] = dialog.scale_box.value()
        QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.Cancel), Qt.LeftButton)
    when_modal(PageSetupDialog, second, failures)
    QTest.keyClick(w.view, Qt.Key_Escape)
    settle(10)
    assert not failures, failures
    assert seen["scale"] == pytest.approx(80.0)
    assert w.undo_stack.count() == 0


# ---------------------------------------------------------------------------
# Clear, Fit to Media
# ---------------------------------------------------------------------------

def test_clear_resets_offset_scale_and_rotation(drawn):
    w = drawn

    def steps(d):
        type_into(d.scale_box, "40")
        type_into(d.offset_x, "15")
        type_into(d.rotation, "30")
        click(d.clear_button)
        assert (d.scale_box.value(), d.offset_x.value(), d.offset_y.value(),
                d.rotation.value()) == (100.0, 0.0, 0.0, 0.0)
        assert not d.auto_scale.isChecked()
    page_setup(w, steps)
    assert w.undo_stack.count() == 0                # nothing left to change


def test_fit_to_media_top_left_from_its_dropdown(drawn):
    w = drawn
    failures = []

    def steps(d):
        pick(d.media, "A2")
        click(d.auto_scale)                          # off
        click(d.clear_button)

        def choose(menu):
            action = next(a for a in menu.actions() if a.text() == "Top Left")
            QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier,
                             menu.actionGeometry(action).center())
        when_popup(choose, failures)
        button = d.fit_button
        QTest.mouseClick(button, Qt.LeftButton, Qt.NoModifier,
                         QPoint(button.width() - 5, button.height() // 2))
        settle()
        assert d.auto_scale.isChecked()
        assert (d.offset_x.value(), d.offset_y.value()) == (0.0, 0.0)
    page_setup(w, steps)
    assert not failures, failures
    a2 = (594 * MM_TO_PT, 420 * MM_TO_PT)
    factor = min(a2[0] / A4_WIDE[0], a2[1] / A4_WIDE[1])
    assert size_of(w) == pytest.approx(a2, abs=0.01)
    landed = centre_of(cloud(w))
    assert landed.x() == pytest.approx(450 * factor, abs=0.6)
    assert landed.y() == pytest.approx(350 * factor, abs=0.6)
    document, page = saved_page(w)
    assert red_at(page, 200 * factor, 150 * factor)
    document.close()


def test_fit_to_media_button_centres(drawn):
    w = drawn

    def steps(d):
        pick(d.media, "A3")
        click(d.auto_scale)
        click(d.clear_button)
        click(d.fit_button)                         # the button itself: Centre
        assert d.auto_scale.isChecked()
        assert d.offset_y.value() > 0
    page_setup(w, steps)
    factor = min(A3_WIDE[0] / A4_WIDE[0], A3_WIDE[1] / A4_WIDE[1])
    assert w.document.pages[0].scale.ratio() == pytest.approx(100 / factor)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def test_pages_custom_range_1_and_3(drawn):
    w = drawn

    def steps(d):
        pick(d.pages.combo, "Custom")
        QTest.mouseClick(d.pages.range, Qt.LeftButton)
        QTest.keyClick(d.pages.range, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClicks(d.pages.range, "1,3")
        settle()
        assert d.page_indexes() == [0, 2]
        click(d.next_page)                          # the preview steps to page 3
        assert d.preview_index == 2
        pick(d.media, "A3")
    page_setup(w, steps)
    assert size_of(w, 0) == pytest.approx(A3_WIDE, abs=0.01)
    assert size_of(w, 1) == pytest.approx(A4_WIDE, abs=0.01)
    assert size_of(w, 2) == pytest.approx(A3_WIDE, abs=0.01)
    assert w.undo_stack.count() == 1
    document, page = saved_page(w, 2)
    assert page.rect.width == pytest.approx(A3_WIDE[0], abs=0.1)
    assert document[1].rect.width == pytest.approx(A4_WIDE[0], abs=0.1)
    factor = A3_WIDE[0] / A4_WIDE[0]
    assert red_at(page, 200 * factor, 150 * factor + 1)
    document.close()
    QTest.keyClick(w.view, Qt.Key_Z, Qt.ControlModifier)
    settle()
    assert [size_of(w, i) for i in range(3)] == [pytest.approx(A4_WIDE, abs=0.01)] * 3


def test_pages_selected_in_thumbnails(drawn):
    w = drawn
    listed = w.pages_panel.list
    for row, modifier in ((1, Qt.NoModifier), (2, Qt.ShiftModifier)):
        rect = listed.visualItemRect(listed.item(row))
        QTest.mouseClick(listed.viewport(), Qt.LeftButton, modifier, rect.center())
    settle()
    assert w.selected_pages() == [1, 2]

    def steps(d):
        assert d.pages.which() == d.pages.SELECTED
        assert d.page_indexes() == [1, 2]
        pick(d.media, "A3")
    page_setup(w, steps)
    assert [size_of(w, i) for i in range(3)] == [
        pytest.approx(A4_WIDE, abs=0.01), pytest.approx(A3_WIDE, abs=0.01),
        pytest.approx(A3_WIDE, abs=0.01)]


def test_pages_current_from_a_pages_own_menu(drawn):
    w = drawn

    def from_page_menu(window):
        menu = window.page_menu(2)
        action = next(a for a in menu.actions() if a.text() == "Page Setup…")
        action.trigger()

    def steps(d):
        assert d.pages.which() == d.pages.CURRENT
        assert d.page_indexes() == [2]
        assert d.pages.combo.currentText() == "Current (3)"
        pick(d.media, "A3")
    page_setup(w, steps, opener=from_page_menu)
    assert [size_of(w, i) for i in range(3)] == [
        pytest.approx(A4_WIDE, abs=0.01), pytest.approx(A4_WIDE, abs=0.01),
        pytest.approx(A3_WIDE, abs=0.01)]


def test_all_pages_in_one_undo_step(drawn):
    w = drawn
    before = state(w)
    page_setup(w, lambda d: (pick(d.pages.combo, "All Pages"), pick(d.media, "A3")))
    assert all(size_of(w, i) == pytest.approx(A3_WIDE, abs=0.01) for i in range(3))
    after = state(w)
    undo_redo_round_trip(w, before, after)


# ---------------------------------------------------------------------------
# Margins (CalcForge), the Page panel, the preview
# ---------------------------------------------------------------------------

def test_margins_keep_their_own_group(drawn):
    w = drawn

    def steps(d):
        assert d.findChild(type(d.margins["margin_left"].parent()),
                           "pageSetupMargins").title() == "Margins (CalcForge)"
        type_into(d.margins["margin_left"], "25")
    page_setup(w, steps)
    page = w.document.pages[0]
    assert page.setup.margin_left == pytest.approx(25.0)
    assert size_of(w) == pytest.approx(A4_WIDE, abs=0.01)
    assert centre_of(cloud(w)).x() == pytest.approx(450, abs=0.6)   # nothing moved


def test_the_page_panel_follows_the_dialog_and_back(drawn):
    w = drawn
    panel = w.page_panel
    page_setup(w, lambda d: pick(d.media, "A3"))
    assert panel.size.currentText() == "A3"
    assert panel.orientation.currentText() == "Landscape"
    # and the panel's own paper box: the paper changes, the drawing stays
    where = centre_of(cloud(w))
    panel.size.setFocus()
    index = panel.size.findText("A2")
    panel.size.setCurrentIndex(index)
    panel.size.activated.emit(index)
    settle()
    assert size_of(w) == pytest.approx((594 * MM_TO_PT, 420 * MM_TO_PT), abs=0.01)
    assert centre_of(cloud(w)) == where
    seen = page_setup(w, lambda d: None, ok=False)
    assert seen["media"] == "594.0 × 420.0"
    document, page = saved_page(w)
    assert page.rect.width == pytest.approx(594 * MM_TO_PT, abs=0.1)
    document.close()


def test_preview_shows_the_media_page_and_scale(drawn):
    w = drawn

    def steps(d):
        assert d.page_value.text() == "297.0 × 209.9"
        pick(d.media, "A3")
        assert d.media_value.text() == "420.0 × 297.0"
        assert d.picture() is not None
        sheet, _factor = d.preview.sheet_rect()
        assert sheet.width() > sheet.height()            # landscape paper
        image = d.preview.grab().toImage()
        middle = image.pixelColor(int(sheet.center().x()), int(sheet.center().y()))
        assert middle.lightness() > 200                   # the white sheet
    page_setup(w, steps, ok=False)


def test_ok_with_nothing_changed_adds_no_step(drawn):
    w = drawn
    page_setup(w, lambda d: None)
    assert w.undo_stack.count() == 0


def test_a_page_turned_in_its_file_resizes_the_way_it_shows(window, tmp_path):
    path = tmp_path / "turned.pdf"
    made = pymupdf.open()
    page = made.new_page(width=595, height=842)            # portrait in the file
    page.draw_rect(pymupdf.Rect(*RED), color=(1, 0, 0), fill=(1, 0, 0))
    page.set_rotation(90)                                  # shown landscape
    made.save(str(path))
    made.close()
    window.show()
    window.open_from_command_line(str(path))
    window.document.path = str(tmp_path / "saved.pdf")
    assert size_of(window) == pytest.approx((842, 595), abs=0.5)
    shown = pymupdf.open(str(path))[0]
    block = shown.get_pixmap(dpi=72)
    reds = [(x, y) for x in range(0, block.width, 4) for y in range(0, block.height, 4)
            if block.pixel(x, y)[0] > 200 and block.pixel(x, y)[1] < 80]
    centre = (sum(x for x, _ in reds) / len(reds), sum(y for _, y in reds) / len(reds))
    page_setup(window, lambda d: (click(d.auto_scale), click(d.clear_button),
                                  type_into(d.scale_box, "50")))
    document, saved = saved_page(window)
    assert saved.rotation == 0
    assert red_at(saved, centre[0] * 0.5, centre[1] * 0.5)
    document.close()


# ---------------------------------------------------------------------------
# everything else on a page goes with it
# ---------------------------------------------------------------------------

def test_equations_and_tables_are_scaled_with_the_page_and_saved(window, tmp_path):
    from tests.test_calc_panels import an_equation
    from tests.test_tables import make_table
    from calcforge.items.calc import CalcItem
    from calcforge.items.table import TableItem
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    first = an_equation(window, "a:=2", 100, 120)
    an_equation(window, "a+1=", 100, 200)
    window.toggle_calc_mode(False)
    table = make_table(window, 300, 400)
    window.view.tables.close()
    settle()
    window.document.path = str(tmp_path / "calc.pdf")
    window.undo_stack.clear()
    before = {type(i).__name__ + str(round(i.pos().y())): i.pos()
              for i in window.document.pages[0].frame.markups()}
    page_setup(window, lambda d: pick(d.media, "A3"))              # Auto Scale
    factor = 420 / 297
    page = window.document.pages[0]
    assert (page.width_pt, page.height_pt) == pytest.approx((297 * MM_TO_PT, 420 * MM_TO_PT),
                                                            abs=0.01)
    items = page.frame.markups()
    sums = [i for i in items if isinstance(i, CalcItem)]
    assert len(sums) == 2
    for item in sums + [i for i in items if isinstance(i, TableItem)]:
        assert item.transform().m11() == pytest.approx(factor, abs=1e-4)
    moved = sorted((i.pos().x(), i.pos().y()) for i in sums)
    was = sorted((p.x(), p.y()) for k, p in before.items() if k.startswith("CalcItem"))
    for (x, y), (x0, y0) in zip(moved, was):
        assert x == pytest.approx(x0 * factor, abs=0.6)
        assert y == pytest.approx(y0 * factor, abs=0.6)
    from calcforge.calc.engine.display import display_text
    answer = max(sums, key=lambda i: i.pos().y())
    assert display_text(answer.region.display) == "3"            # still worked out
    document, saved = saved_page(window)
    assert saved.rect.height == pytest.approx(420 * MM_TO_PT, abs=0.1)
    assert "a" in saved.get_text()
    document.close()
    # opened again it is as it was saved
    window.open_from_command_line(window.document.path)
    settle()
    again = window.document.pages[0].frame.markups()
    assert sorted((round(i.pos().x(), 1), round(i.pos().y(), 1)) for i in again
                  if isinstance(i, CalcItem)) == [(round(x, 1), round(y, 1)) for x, y in moved]
    assert all(i.transform().m11() == pytest.approx(factor, abs=1e-4)
               for i in again if isinstance(i, (CalcItem, TableItem)))
    assert first is not None


def test_a_markup_from_the_file_is_not_written_twice(window, tmp_path):
    path = tmp_path / "marked.pdf"
    made = pymupdf.open()
    page = made.new_page(width=A4_WIDE[0], height=A4_WIDE[1])
    page.draw_rect(pymupdf.Rect(*RED), color=(1, 0, 0), fill=(1, 0, 0))
    square = page.add_rect_annot(pymupdf.Rect(400, 300, 500, 400))
    square.set_colors(stroke=(0, 0, 1))
    square.update()
    made.save(str(path))
    made.close()
    window.show()
    window.open_from_command_line(str(path))
    window.document.path = str(tmp_path / "saved.pdf")
    assert window.document.pages[0].markup_annotations
    page_setup(window, lambda d: (click(d.auto_scale), click(d.clear_button),
                                  type_into(d.scale_box, "50")))
    page = window.document.pages[0]
    assert page.markup_annotations == []
    (item,) = page.frame.markups()
    assert not item.still_theirs
    assert centre_of(item).x() == pytest.approx(225, abs=0.6)
    document, saved = saved_page(window)
    boxes = [a.rect for a in saved.annots()]
    assert len(boxes) == 1, boxes
    assert (boxes[0].x0 + boxes[0].x1) / 2 == pytest.approx(225, abs=1)
    assert (boxes[0].y0 + boxes[0].y1) / 2 == pytest.approx(175, abs=1)
    document.close()


def test_viewports_and_bookmarks_follow_and_undo_puts_them_back(drawn):
    w = drawn
    from calcforge.core.document import Viewport
    page = w.document.pages[0]
    page.viewports.append(Viewport("Detail", 400, 300, 100, 100, PageScale.from_ratio(20)))
    w.document.add_bookmark("Block", 0, y=150.0)
    before = state(w)
    page_setup(w, lambda d: (click(d.auto_scale), click(d.clear_button),
                             type_into(d.scale_box, "50")))
    page = w.document.pages[0]
    (viewport,) = page.viewports
    assert (viewport.x, viewport.y, viewport.width) == pytest.approx((200, 150, 50))
    assert viewport.scale.ratio() == pytest.approx(40)
    assert w.document.bookmarks[-1].y == pytest.approx(75)
    after = state(w)
    undo_redo_round_trip(w, before, after)


def test_a_picture_page_is_drawn_again_onto_its_new_paper(window, tmp_path):
    from PySide6.QtGui import QColor, QImage
    picture = QImage(842, 595, QImage.Format_RGB32)
    picture.fill(QColor("white"))
    for x in range(100, 300):
        for y in range(100, 200):
            picture.setPixelColor(x, y, QColor("red"))
    path = tmp_path / "scan.png"
    picture.save(str(path))
    from calcforge.io import pdfio
    window.show()
    window._structural_change("Insert image page", lambda: pdfio.import_image(
        window.document, str(path), pdfio.FIT_ORIGINAL, at=1))
    window.go_to_page(1)
    page = window.document.pages[1]
    old_key = page.background_key
    width, height = page.width_pt, page.height_pt
    page_setup(window, lambda d: (click(d.auto_scale), click(d.clear_button),
                                  type_into(d.scale_box, "50")))
    page = window.document.pages[1]
    assert (page.width_pt, page.height_pt) == pytest.approx((width, height))
    assert page.background_key != old_key
    image = QImage()
    image.loadFromData(window.document.asset(page.background_key))
    assert image.size() == picture.size()                 # as dense as it was
    red = image.pixelColor(100, 75)                       # the block's middle, halved
    assert red.red() > 200 and red.green() < 80
    assert image.pixelColor(250, 180).red() > 200 and image.pixelColor(250, 180).green() > 200
    assert image.pixelColor(600, 400).alpha() == 0        # off the halved picture: paper


def test_fifty_pages_go_quickly(window, tmp_path):
    """The whole drawing set in one go (the user: "should be fast")."""
    import time
    from calcforge.items.shapes import PolyItem
    path = tmp_path / "set.pdf"
    _drawing(path, pages=50)
    window.show()
    window.open_from_command_line(str(path))
    for page in window.document.pages:
        for n in range(20):
            item = PolyItem("polyline")
            item.points = [QPointF(0, 0), QPointF(100, 20), QPointF(200, 0)]
            page.frame.add_markup(item)
            item.setPos(100 + n * 30, 100 + n * 20)
    dialog = window.page_setup_dialog()
    dialog.pages.choose(dialog.pages.ALL)
    dialog.choose_media("A3", landscape=True)
    started = time.perf_counter()
    assert window.finish_page_setup(dialog)
    took = time.perf_counter() - started
    assert all(size_of(window, i) == pytest.approx(A3_WIDE, abs=0.01) for i in range(50))
    assert took < 4.0, took            # about 0.8 s on the development machine
    started = time.perf_counter()
    window.undo_stack.undo()
    assert time.perf_counter() - started < 4.0
    assert size_of(window, 49) == pytest.approx(A4_WIDE, abs=0.01)


# ---------------------------------------------------------------------------
# Thumbnails: going to another page picks it alone (2026-10-17)
# ---------------------------------------------------------------------------

def pick_in_thumbnails(window, first, last):
    """Click one thumbnail and Shift-click another, as a person picks a run."""
    listed = window.pages_panel.list
    for row, modifier in ((first, Qt.NoModifier), (last, Qt.ShiftModifier)):
        listed.scrollToItem(listed.item(row))
        rect = listed.visualItemRect(listed.item(row))
        QTest.mouseClick(listed.viewport(), Qt.LeftButton, modifier, rect.center())
    settle()


def press(window, key, modifiers=Qt.NoModifier):
    window.activateWindow()
    settle()
    QTest.keyClick(window.view, key, modifiers)
    settle()


def test_set_scale_then_another_page_picks_that_page_alone(drawn):
    """Set Scale on All Pages re-picked page 1 in Thumbnails, and every page
    gone to after it was added to it: Page Setup then opened on Selected."""
    from calcforge.ui.dialogs import ScaleDialog
    w = drawn
    failures = []

    def apply_to_all(dialog):
        pick(dialog.pages.combo, "All Pages")
        click(dialog.apply_button)
    when_modal(ScaleDialog, apply_to_all, failures)
    w.act_scale.trigger()
    settle()
    assert not failures, failures
    assert w.selected_pages() == [0]
    press(w, Qt.Key_End)
    assert w.selected_pages() == [2]
    press(w, Qt.Key_Left, Qt.ControlModifier)
    assert w.selected_pages() == [1]
    seen = {}
    page_setup(w, lambda d: seen.update(which=d.pages.which(), pages=d.page_indexes()),
               ok=False)
    assert seen == {"which": "current", "pages": [1]}


@pytest.mark.parametrize("command", ["page setup", "crop pages", "set scale"])
def test_a_run_stays_picked_after_a_command_and_going_on_replaces_it(drawn, command):
    w = drawn
    pick_in_thumbnails(w, 0, 1)
    assert w.selected_pages() == [0, 1]
    if command == "page setup":
        page_setup(w, lambda d: pick(d.media, "A3"))
        assert size_of(w, 1) == pytest.approx(A3_WIDE, abs=0.01)
    elif command == "crop pages":
        dialog = w.crop_pages_dialog()
        assert dialog.page_indexes() == [0, 1]
        for box in dialog.findChildren(type(w.page_panel.width_mm)):
            box.setValue(10.0)
        w.finish_crop_pages(dialog)
        assert size_of(w, 1)[0] < A4_WIDE[0] - 1
    else:
        w.set_page_scale(PageScale.from_ratio(50), [0, 1])
    assert w.selected_pages() == [0, 1]            # what it was done to, still picked
    press(w, Qt.Key_End)
    assert w.selected_pages() == [2]               # and going on picks the page alone
    press(w, Qt.Key_Home)
    assert w.selected_pages() == [0]


@pytest.fixture
def six(window, tmp_path):
    """Six A4 landscape sheets, pages 2-4 picked in Thumbnails by mouse, the
    view on page 4 at 100 %."""
    path = tmp_path / "six.pdf"
    _drawing(path, pages=6)
    window.show()
    window.activateWindow()
    window.open_from_command_line(str(path))
    window.view.set_zoom(1.0)
    settle()
    pick_in_thumbnails(window, 1, 3)
    assert window.selected_pages() == [1, 2, 3]
    return window


def wheel(window, notches, modifiers=Qt.NoModifier):
    """Turn the wheel near the top of the view, so a zoom swings the middle
    of the view onto other pages."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent
    view = window.view
    middle = QPointF(view.viewport().rect().center().x(), 20)
    for _ in range(abs(notches)):
        event = QWheelEvent(middle, view.viewport().mapToGlobal(middle.toPoint()),
                            QPoint(0, 0), QPoint(0, 120 if notches > 0 else -120),
                            Qt.NoButton, modifiers, Qt.NoScrollPhase, False)
        QApplication.sendEvent(view.viewport(), event)
        settle(2)
    view.finish_scrolling()
    settle()


def test_zooming_keeps_the_run_picked_in_thumbnails(six):
    """A zoom scrolls past other pages on its way: the picked run stays
    picked and only the page in view moves (the coordinator, 2026-10-17)."""
    w = six
    seen = set()
    w.view.pageChanged.connect(seen.add)            # every page the view passed

    def check(what):
        assert w.selected_pages() == [1, 2, 3], what

    wheel(w, -12)                                   # the plain wheel zooms out
    assert w.view.zoom() < 0.5
    check("wheel out")
    wheel(w, 12)                                    # and back in
    check("wheel in")
    # With Preferences ▸ the wheel set to scroll, Ctrl+wheel is the zoom
    from calcforge.ui import preferences
    prefs = preferences.current()
    was = prefs.wheel
    prefs.wheel = preferences.WHEEL_SCROLL
    try:
        wheel(w, -10, Qt.ControlModifier)
        assert w.view.zoom() < 0.5
        check("ctrl+wheel out")
        wheel(w, 10, Qt.ControlModifier)
        check("ctrl+wheel in")
    finally:
        prefs.wheel = was
    press(w, Qt.Key_9, Qt.ControlModifier)          # Fit Page
    check("ctrl+9")
    press(w, Qt.Key_0, Qt.ControlModifier)          # Fit Width
    check("ctrl+0")
    for choice in ("25%", "Fit Page", "200%", "Fit Width"):
        pick(w.zoom_combo, choice, shown=False)     # the zoom box, by mouse
        settle()
        check(choice)
    assert len(seen - {3}) >= 2, seen               # the zooms did pass other pages
    # the run is still what Page Setup offers
    seen_dialog = {}
    page_setup(w, lambda d: seen_dialog.update(pages=d.page_indexes()), ok=False)
    assert seen_dialog["pages"] == [1, 2, 3]


def test_going_to_a_page_after_a_zoom_still_picks_it_alone(six):
    w = six
    wheel(w, -12)
    assert w.selected_pages() == [1, 2, 3]
    press(w, Qt.Key_End)
    assert w.selected_pages() == [5]
    wheel(w, 12)                                    # one page picked: it follows the view
    assert w.selected_pages() == [w.current_index]
