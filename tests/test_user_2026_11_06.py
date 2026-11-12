"""The user's 2026-11-06 report, in a window: a second window on the same
document closed leaves nothing behind that breaks the first (the Variables
panel's deleted timer); a click on a workbook's page picture in Thumbnails
goes to the page and does not unfold the workbook; a tool set made at a scale
puts its tools down at their real size on a scaled page (Revu's Set Scale)."""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

openpyxl = pytest.importorskip("openpyxl")


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


def test_a_second_window_on_the_document_closed_leaves_the_first_working(w):
    """A tab's New Window shows the document in a second window; closing
    that window took its Variables panel with it and left the panel's calls
    on the document's sheet and book, and every equation placed and page
    pasted in the first window then failed on the panel's deleted timer
    (the user, 2026-11-06: "libshiboken: Internal C++ object (QTimer)
    already deleted")."""
    import shiboken6

    from calcforge.calc.docsheet import sheet_for
    from calcforge.sheet.docbook import book_for
    from tests.test_calc_editing import type_line
    sheet = sheet_for(w.document)
    book = book_for(w.document)
    other = w.open_same_document_window()
    pump(0.2)
    assert other is not w and other.document is w.document
    panel = other.variables_panel
    assert panel._soon in sheet.listeners and panel._soon_for_tables in book.listeners
    other.confirm_discard = lambda: True
    other.close()
    other.deleteLater()
    pump(0.3)
    assert not shiboken6.isValid(panel)
    assert panel._soon not in sheet.listeners, "the closed window's panel left the sheet's list"
    assert panel._soon_for_tables not in book.listeners, "and the book's"
    # an equation placed in the window still open: calculated, nothing raised
    frame = w.document.pages[0].frame
    w.toggle_calc_mode(True)
    w.view.calc.place_cross(frame, QPointF(60, 60))
    type_line(w, "t:5")
    w.toggle_calc_mode(False)
    pump(0.2)
    sheet.recalculate()
    assert any(getattr(r, "defined_vars", None) for r in sheet.worksheet.regions) \
        or any("t" in str(getattr(r, "defined_vars", "")) for r in sheet.worksheet.regions)
    # a page added (a structural change: the book and the sheet both report)
    before = len(w.document.pages)
    w.quick_add_page(before - 1)
    pump(0.2)
    assert len(w.document.pages) == before + 1


def test_a_listener_whose_window_has_gone_is_dropped_not_fatal(w):
    """Belt and braces: a listener that raises Qt's deleted-object error is
    taken off the list and the others are still told."""
    from calcforge.calc.docsheet import sheet_for
    from calcforge.sheet.docbook import book_for
    told = []

    def dead():
        raise RuntimeError("libshiboken: Internal C++ object (PySide6.QtCore.QTimer) already deleted.")

    def dead_for_tables(_keys):
        raise RuntimeError("libshiboken: Internal C++ object (PySide6.QtCore.QTimer) already deleted.")

    sheet = sheet_for(w.document)
    book = book_for(w.document)
    sheet.listeners.insert(0, dead)
    sheet.listeners.append(lambda: told.append("sheet"))
    book.listeners.insert(0, dead_for_tables)
    book.listeners.append(lambda keys: told.append("book"))
    try:
        sheet._report()
        book._changed({("layout", 1)})
    finally:
        for listener in list(sheet.listeners):
            if listener is dead or getattr(listener, "__name__", "") == "<lambda>":
                sheet.listeners.remove(listener)
        for listener in list(book.listeners):
            if listener is dead_for_tables or getattr(listener, "__name__", "") == "<lambda>":
                book.listeners.remove(listener)
    assert told == ["sheet", "book"]
    assert dead not in sheet.listeners and dead_for_tables not in book.listeners
    # any other error still comes through
    def wrong():
        raise RuntimeError("something else")
    sheet.listeners.append(wrong)
    try:
        with pytest.raises(RuntimeError, match="something else"):
            sheet._report()
    finally:
        sheet.listeners.remove(wrong)


def test_a_click_on_a_folded_workbooks_page_goes_to_it_and_does_not_unfold_it(w, tmp_path):
    """Thumbnails shows a workbook as one entry, its first page on a stack of
    sheets; the ▸ name line under it unfolds it. A click on the page picture
    itself goes to the page and leaves the workbook folded (the user,
    2026-11-06: "clicking on grey part of thumbnail expands it")."""
    from calcforge.ui.panels import SECTION_ROLE
    from tests.test_workbook_sections import head_rect, with_loads
    section = with_loads(w, tmp_path, no_print=("Loads", "Factors"))
    w.show_panel("dock_pages", True)
    pump()
    listed = w.pages_panel.list
    head = listed.item(section.first)
    assert head.data(SECTION_ROLE)["collapsed"]
    assert all(listed.isRowHidden(row) for row in section.pages[1:])
    w.go_to_page(0)
    pump()
    picture = listed.picture_rect(section.first)
    for spot in (picture.center(), picture.topLeft() + QPointF(3, 3).toPoint(),
                 picture.bottomRight() - QPointF(3, 3).toPoint()):
        QTest.mouseClick(listed.viewport(), Qt.LeftButton, Qt.NoModifier, spot)
        pump(0.1)
        assert w.current_index == section.first, "the click goes to the page"
        assert listed.item(section.first).data(SECTION_ROLE)["collapsed"], \
            "and the workbook stays folded"
        assert all(listed.isRowHidden(row) for row in section.pages[1:])
    # the name line still unfolds it
    words = listed.delegate.toggle_rect(head_rect(w, section))
    QTest.mouseClick(listed.viewport(), Qt.LeftButton, Qt.NoModifier, words.center())
    pump(0.1)
    assert not any(listed.isRowHidden(row) for row in section.pages)


def test_a_tool_set_made_at_a_scale_puts_its_tools_down_at_their_real_size(w):
    """Revu's Set Scale on a tool set (the user, 2026-11-06: "add set scale
    to toolsets similar to Bluebeam"): the set's gear menu has Set Scale…,
    the scale shows on the set's header, and a Drawing Mode tool from the
    set comes down at its real size on a page with a scale — a door kept at
    1:50 is half the size on a 1:100 plan — and as kept on a page without
    one. Remove Scale takes it off."""
    from PySide6.QtCore import QRectF

    from calcforge.core.document import PT_TO_MM, PageScale
    from calcforge.items.shapes import RectItem
    from calcforge.ui import toolsets
    panel = w.toolsets_panel
    w.show_panel("dock_toolsets", True)
    pump()
    frame = w.document.pages[0].frame
    door = RectItem("rect")
    door.set_local_rect(QRectF(0, 0, 100, 50))
    frame.add_markup(door, QPointF(80, 80))
    pump()
    entry = toolsets.entry_for(door)            # kept off a page with no scale of its own
    assert not entry.scaled and entry.mm_per_pt == 0.0
    panel.groups.append(toolsets.ToolSet("Doors", [entry]))
    toolsets.save_toolsets(panel.groups)
    panel.rebuild(keep="Doors")
    try:
        group = next(g for g in panel.groups if g.name == "Doors")
        assert group.mm_per_pt() == 0.0 and group.scale_label == ""
        panel.select_set("Doors")
        names = [a.text() for a in panel.build_set_menu().actions()]
        assert "Set Scale…" in names and "Remove Scale" not in names
        panel.apply_set_scale(group, PageScale.from_ratio(50))
        group = next(g for g in panel.groups if g.name == "Doors")
        assert group.scale_label == "1:50"
        assert abs(group.mm_per_pt() - 50 * PT_TO_MM) < 1e-6
        header = next(panel.tree.topLevelItem(i) for i in range(panel.tree.topLevelItemCount())
                      if panel.tree.topLevelItem(i).data(0, panel.SET_ROLE) == "Doors")
        assert "1:50" in header.text(0)
        panel.select_set("Doors")
        names = [a.text() for a in panel.build_set_menu().actions()]
        assert "Set Scale…" in names and "Remove Scale" in names
        # kept again on reopening the sets
        assert next(g for g in toolsets.load_toolsets() if g.name == "Doors").scale_label == "1:50"

        def placed_width(frame, at):
            before = set(frame.markups())
            w.use_tool_entry(group.entries[0], group)
            assert w.view.place_pending_stamp(frame.mapToScene(at))
            pump()
            new = [m for m in frame.markups() if m not in before]
            assert len(new) == 1
            return new[0].mapRectToScene(new[0].local_rect()).width()

        w.set_page_scale(PageScale.from_ratio(100), [0])
        pump()
        assert abs(placed_width(frame, QPointF(300, 300)) - 50.0) < 0.5, "half the size at 1:100"
        w.quick_add_page(0)
        pump()
        plain = w.document.pages[1].frame
        assert not plain.page.scale.calibrated
        assert abs(placed_width(plain, QPointF(300, 300)) - 100.0) < 0.5, "as kept with no scale"
        # the tool's own Scale goes first: one kept off a 1:200 page
        own = toolsets.ToolEntry.from_dict(dict(entry.to_dict(), scaled=True,
                                                mm_per_pt=200 * PT_TO_MM))
        group.entries.append(own)
        w.use_tool_entry(own, group)
        before = set(frame.markups())
        assert w.view.place_pending_stamp(frame.mapToScene(QPointF(300, 500)))
        pump()
        new = next(m for m in frame.markups() if m not in before)
        assert abs(new.mapRectToScene(new.local_rect()).width() - 200.0) < 0.5
        # Remove Scale: as kept, whatever the page
        panel.select_set("Doors")
        panel.remove_scale_of_set()
        group = next(g for g in panel.groups if g.name == "Doors")
        assert group.scale is None and group.scale_label == ""
        assert abs(placed_width(frame, QPointF(300, 700)) - 100.0) < 0.5
    finally:
        panel.groups = [g for g in panel.groups if g.name != "Doors"]
        toolsets.save_toolsets(panel.groups)
        panel.rebuild()
