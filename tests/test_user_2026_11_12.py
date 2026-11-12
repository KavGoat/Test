"""The user's 2026-11-12 report, in a window: Alt+Z while typing fits the
box, ends the typing and leaves the box picked; a PDF dropped on a page goes
in after it and the drag says so, dropped off the pages it opens in a tab; an
equation's Set as Default makes the next equations its size and colour; the
Properties toolbar shows an equation's size, colour and result fields; Offset
is on a markup's right-click menu and follows the pointer until a distance is
typed."""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, QRectF, Qt, QUrl
from PySide6.QtGui import QDragMoveEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

pymupdf = pytest.importorskip("pymupdf")


def pump(seconds=0.0):
    end = time.monotonic() + seconds
    QApplication.processEvents()
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    window.confirm_discard = lambda: True
    pump()
    return window


def a_box(w, text, width=260.0):
    from calcforge.items.text import TextItem
    frame = w.document.pages[0].frame
    item = TextItem(text, QRectF(0, 0, width, 120))
    frame.add_markup(item, QPointF(60, 60))
    item.apply_style()
    pump(0.1)
    return item


def test_alt_z_while_typing_fits_the_box_ends_the_typing_and_leaves_it_picked(w):
    """The user, 2026-11-12: "Alt z did not work while typing in a text box,
    it should resize and exit the text box edit mode and go into selected
    mode"."""
    box = a_box(w, "A few words")
    tall = box.local_rect().height()
    view = w.view
    view.begin_item_edit(box)
    pump(0.1)
    assert view.editing_item() is box
    QTest.keyClick(view.viewport(), Qt.Key_Z, Qt.AltModifier)
    pump(0.2)
    assert view.editing_item() is None, "the typing is over"
    assert box.isSelected() and w.selected_items() == [box], "the box is picked"
    assert box.local_rect().height() < tall, "and fitted round its words"


def _drag(w, path, where):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    view = w.view
    point = view.mapFromScene(where)
    event = QDragMoveEvent(point, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    view.dragEnterEvent(event)
    view.dragMoveEvent(event)
    pump()
    return mime, point


def test_a_pdf_dropped_on_a_page_goes_in_after_it_and_off_the_pages_opens(w, tmp_path):
    """The user, 2026-11-12: "dragging a document from explorer shows copy
    instead of open, it depends if I am hovering in [the] view which would
    be insert, or dragging in the tab bar which would be open"."""
    path = tmp_path / "two.pdf"
    with pymupdf.open() as made:
        for words in ("one", "two"):
            page = made.new_page(width=300, height=200)
            page.insert_text((40, 60), words, fontsize=24)
        made.save(str(path))
    w.quick_add_page(0)
    pump(0.1)
    assert len(w.document.pages) == 2
    frame = w.document.pages[0].frame
    mime, point = _drag(w, path, frame.mapToScene(frame.page_rect().center()))
    assert w.view._drop_after is frame, "a line under the page it goes in after"
    assert w.status_hint.text() == "Drop to put the PDF's pages in after page 1"
    view = w.view
    drop = QDropEvent(point, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    view.dropEvent(drop)
    pump(0.3)
    assert len(w.document.pages) == 4, "its two pages came in"
    assert [round(p.width_pt) for p in w.document.pages[1:3]] == [300, 300]
    assert w.document.pages[1].pdf_key and w.document.pages[2].pdf_key
    assert w.document_tabs.count() == 1, "nothing opened in a tab"
    # off the pages (the canvas's margin): it would open in a tab
    far = view.mapToScene(QPoint(view.viewport().width() - 2, view.viewport().height() - 2))
    _drag(w, path, far)
    if view.drop_target(far) is None:
        assert w.status_hint.text() == "Drop to open in a tab of its own"
    # the window (the tab bar, a panel) opens it
    w.status_hint.setText("")
    event = QDragMoveEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    w.dragEnterEvent(event)
    w.dragMoveEvent(event)
    assert w.status_hint.text() == "Drop to open the PDF in a tab of its own"
    tabs = w.document_tabs.count()
    w.drop_files([str(path)])
    pump(0.3)
    assert w.document_tabs.count() == tabs + 1, "opened in a tab of its own"


def test_an_equations_set_as_default_makes_the_next_ones_its_size_and_colour(w):
    """The user, 2026-11-12: "equation set default not working when I change
    font size"."""
    from calcforge.calc.docsheet import sheet_for
    from calcforge.ui import preferences
    from tests.test_calc_editing import type_line
    before = preferences.current()
    frame = w.document.pages[0].frame
    w.toggle_calc_mode(True)
    w.view.calc.place_cross(frame, QPointF(60, 100))
    type_line(w, "a:5")
    w.toggle_calc_mode(False)
    pump(0.1)
    item = next(iter(sheet_for(w.document).items.values()))
    try:
        item.region.font_size = 16.0
        item.region.color = "#1971c2"
        item.relayout()
        w.set_as_default(item)
        now = preferences.current()
        assert now.equation_font_size == 16.0 and now.equation_colour == "#1971c2"
        assert "New equations will be 16 pt" in w.status_hint.text()
        w.toggle_calc_mode(True)
        w.view.calc.place_cross(frame, QPointF(60, 200))
        type_line(w, "b:6")
        w.toggle_calc_mode(False)
        pump(0.1)
        new = [i for i in sheet_for(w.document).items.values() if i is not item][0]
        assert new.region.font_size == 16.0 and new.region.color == "#1971c2"
    finally:
        preferences.apply(before)


def test_the_properties_toolbar_shows_an_equations_size_colour_and_result_fields(w):
    """The user, 2026-11-12: "the property toolbar did not show important
    things for the equation like font or colour or whatever else in there in
    the property panel"."""
    from calcforge.calc.docsheet import sheet_for
    from tests.test_calc_editing import type_line
    frame = w.document.pages[0].frame
    w.toggle_calc_mode(True)
    w.view.calc.place_cross(frame, QPointF(60, 100))
    type_line(w, "1/3=")
    w.toggle_calc_mode(False)
    pump(0.1)
    item = next(iter(sheet_for(w.document).items.values()))
    w.scene.clearSelection()
    item.setSelected(True)
    w.refresh_selection()
    pump(0.1)

    def shown(field):
        return [a.defaultWidget() for a in w._style_widgets[field] if a.isVisible()]
    assert w.font_spin in shown("font") and w.text_colour_button in shown("font")
    assert w.font_style_button in shown("font")
    assert w.equation_decimals in shown("equation")
    assert w.equation_significant in shown("equation") and w.equation_zeros in shown("equation")
    assert w.font_spin.value() == item.region.font_size
    worksheet = sheet_for(w.document).worksheet
    assert w.equation_decimals.value() == worksheet.format.decimals
    # the fields change the equation, as the panel's and the menu's do
    w.equation_decimals.setValue(2)
    pump(0.1)
    assert item.region.fmt is not None and item.region.fmt.decimals == 2
    w.equation_significant.setChecked(True)
    pump(0.1)
    assert item.region.fmt.significant
    w.equation_zeros.setChecked(True)
    pump(0.1)
    assert item.region.fmt.trailing_zeros
    w.undo_stack.undo()
    pump(0.1)
    item = next(iter(sheet_for(w.document).items.values()))     # (undo rebuilds it)
    assert not (item.region.fmt or worksheet.format).trailing_zeros, "one undo step each"
    assert (item.region.fmt or worksheet.format).significant, "the step before stays"
    # while it is typed into, too
    w.view.calc.focus(item)
    pump(0.1)
    w.refresh_selection()
    pump(0.1)
    assert w.equation_decimals in shown("equation") and w.font_spin in shown("font")
    w.view.calc.leave()
    pump(0.1)


def test_offset_is_on_the_right_click_menu_and_follows_the_pointer(w):
    """The user, 2026-11-12: "right click then offset does nothing, same with
    in the edit menu". Offset is on a markup's menu, and as Revu's it follows
    the pointer — as far out as the pointer is — until a distance is typed."""
    from calcforge.core.document import PT_TO_MM
    from calcforge.items.shapes import RectItem
    frame = w.document.pages[0].frame
    rect = RectItem("rect")
    rect.set_local_rect(QRectF(0, 0, 120, 60))
    frame.add_markup(rect, QPointF(100, 100))
    pump(0.1)
    view = w.view
    w.scene.clearSelection()
    rect.setSelected(True)
    menu = w.build_context_menu(rect, rect.mapToScene(QPointF(60, 30)))
    names = [a.text() for a in menu.actions()]
    assert "Offset" in names and names.index("Offset") == names.index("Delete") + 1, \
        "after Revu's own entries, which keep Revu's order"
    box = a_box(w, "words")
    w.scene.clearSelection()
    box.setSelected(True)
    assert "Offset" not in [a.text() for a in w.build_context_menu(box, box.mapToScene(QPointF(5, 5))).actions()], \
        "a text box cannot be offset: not offered"
    w.scene.clearSelection()
    rect.setSelected(True)
    w.act_offset.trigger()
    pump(0.1)
    session = w._offset
    assert session is not None and w._offset_bar.isVisible()
    assert session.following and w.offset_distance.text() == ""
    out = view.mapFromScene(rect.mapToScene(QPointF(60, -30)))        # 30 pt above the top
    QTest.mouseMove(view.viewport(), out)
    pump(0.1)
    assert session.distance() == pytest.approx(30.0, abs=1.5)      # (whole screen pixels)
    assert w.offset_distance.text() == f"{session.distance() * PT_TO_MM:.1f} mm", \
        "the toolbar says how far"
    assert session.preview is not None and not session.preview.path().isEmpty()
    before = len(frame.markups())
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, out)
    pump(0.1)
    copies = [m for m in frame.markups() if m is not rect and isinstance(m, RectItem)]
    assert len(frame.markups()) == before + 1 and copies
    assert copies[-1].local_rect().width() == pytest.approx(120 + 2 * session.distance(), abs=0.5)
    # a distance typed holds, whatever the pointer does
    w.scene.clearSelection()
    rect.setSelected(True)
    w.act_offset.trigger()
    pump(0.1)
    session = w._offset
    w.offset_distance.setText("5 mm")
    w.offset_distance.textEdited.emit("5 mm")
    QTest.mouseMove(view.viewport(), view.mapFromScene(rect.mapToScene(QPointF(60, -80))))
    pump(0.1)
    assert not session.following
    assert session.distance() == pytest.approx(5 / PT_TO_MM, abs=0.5)
    session.finish()
