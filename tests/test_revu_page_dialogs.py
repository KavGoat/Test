"""Revu's page dialogs: Insert Blank Page, Insert Pages, Extract Pages, Split
Document, Delete Pages, Crop Pages and Apply to Pages, with the shared Pages
control; Check Spelling's buttons, the Action dialog, Title Case titles and
Rename Page Label in place (the user, 2026-10-16: "Page scale pop up, insert
page pop up, all popups should look nice and follow the same Bluebeam style
and wording").

Dialogs are built by the window's ``*_dialog`` builders, their fields set,
and the accept path (``finish_*``) called: a modal exec never returns
headless.
"""
from __future__ import annotations

import os

import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from calcforge.core.document import MM_TO_PT
from calcforge.items.shapes import RectItem
from calcforge.ui import dialogs
from calcforge.ui.widgets import PagesRange


def _pages(window, count):
    asking, window.interactive_prompts = window.interactive_prompts, False
    while len(window.document.pages) < count:
        window.add_page()
    window.interactive_prompts = asking
    window.pages_panel.rebuild(window.document, window.current_index)
    window.go_to_page(0)


def _pick(window, rows):
    listing = window.pages_panel.list
    listing.clearSelection()
    for row in rows:
        listing.item(row).setSelected(True)
    return window.selected_pages()


def _rect(window, page=0, at=(100, 100)):
    frame = window.document.pages[page].frame
    item = RectItem("rect", QRectF(0, 0, 80, 40))
    frame.add_markup(item, QPointF(*at))
    return item


def _rects(window, page):
    frame = window.document.pages[page].frame
    return [i for i in frame.markups() if isinstance(i, RectItem)]


def _opened(monkeypatch, cls):
    """Record each dialog of *cls* opened, and cancel it."""
    seen = []
    monkeypatch.setattr(cls, "exec", lambda self: seen.append(self) or QDialog.Rejected)
    return seen


def _pdf(path, sizes):
    import pymupdf
    with pymupdf.open() as pdf:
        for width, height in sizes:
            page = pdf.new_page(width=width, height=height)
            page.insert_text((40, 60), f"{width}x{height}")
        pdf.save(path)
    return path


def _count(path):
    import pymupdf
    with pymupdf.open(path) as pdf:
        return pdf.page_count


# ---------------------------------------------------------------------------
# B0: the shared Pages control
# ---------------------------------------------------------------------------

def test_pages_control_reads_all_current_selected_and_custom(qapp):
    pages = PagesRange(6, current=2, selected=[0, 1, 4])
    try:
        assert [pages.combo.itemText(i) for i in range(pages.combo.count())] == [
            "All Pages", "Current (3)", "Selected", "Custom"]
        assert pages.which() == PagesRange.CURRENT and pages.pages() == [2]
        pages.choose(PagesRange.ALL)
        assert pages.range.text() == "1-6" and pages.pages() == list(range(6))
        pages.choose(PagesRange.SELECTED)
        assert pages.range.text() == "1-2, 5" and pages.pages() == [0, 1, 4]
        pages.range.setText("1-3, 6")
        pages.range.textEdited.emit("1-3, 6")          # typed: Custom
        assert pages.which() == PagesRange.CUSTOM
        assert pages.pages() == [0, 1, 2, 5]
        pages.set_custom("9")                          # past the end: unreadable
        assert pages.page_indexes() is None and pages.pages() == []
    finally:
        pages.deleteLater()
    alone = PagesRange(3, current=0)
    try:
        assert alone.combo.findText("Selected") < 0      # nothing picked
    finally:
        alone.deleteLater()


def test_set_scale_and_flatten_use_the_shared_control(window):
    for dialog in (window.scale_dialog(), window.flatten_dialog()):
        try:
            assert isinstance(dialog.pages, PagesRange)
        finally:
            dialog.deleteLater()


def test_selected_shows_only_with_a_thumbnail_selection(window):
    _pages(window, 4)
    dialog = window.delete_pages_dialog()
    assert dialog.pages.combo.findText("Selected") < 0
    dialog.deleteLater()
    assert _pick(window, [1, 3]) == [1, 3]
    dialog = window.extract_pages_dialog()
    try:
        assert dialog.pages.combo.findText("Selected") >= 0
        assert dialog.pages.which() == PagesRange.SELECTED
        assert dialog.page_indexes() == [1, 3]
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Every way in opens the dialog, with Revu's title
# ---------------------------------------------------------------------------

def _entry(menu, *path):
    for text in path[:-1]:
        menu = next(a for a in menu.actions() if a.text() == text).menu()
    return next(a for a in menu.actions() if a.text() == path[-1])


def test_every_page_dialog_opens_from_its_menus(window, monkeypatch, tmp_path):
    window.interactive_prompts = True
    _pages(window, 3)
    blank = _opened(monkeypatch, dialogs.InsertBlankPageDialog)
    window.act_add_page.trigger()                          # Document ▸ Insert ▸ Blank Page…
    _entry(window.page_menu(1), "Insert Blank Page", "Before…").trigger()
    _entry(window.page_menu(1), "Insert Blank Page", "After…").trigger()
    assert [d.windowTitle() for d in blank] == ["Insert Blank Page"] * 3
    # pre-set: after the page in view; before / after the page right-clicked
    assert [(d.placement.side.currentData(), d.placement.where(),
             d.placement.number.value()) for d in blank] == [
        ("after", "page", 1), ("before", "page", 2), ("after", "page", 2)]
    # under Insert ▸ it is a submenu of Before… / After…, as on the page menu
    assert window.act_add_page.text() == "Blank Page"
    assert [a.text() for a in window.act_add_page.menu().actions()] == ["Before…", "After…"]

    inserting = _opened(monkeypatch, dialogs.InsertPagesDialog)
    window.act_insert_pdf.trigger()
    _entry(window.page_menu(2), "Insert Pages", "Before…").trigger()
    _entry(window.page_menu(2), "Insert Pages", "After…").trigger()
    assert [d.windowTitle() for d in inserting] == ["Insert Pages"] * 3
    assert [(d.placement.side.currentData(), d.placement.number.value())
            for d in inserting] == [("after", 1), ("before", 3), ("after", 3)]

    extracting = _opened(monkeypatch, dialogs.ExtractPagesDialog)
    window.act_extract_pages.trigger()
    _entry(window.page_menu(1), "Extract Pages…").trigger()
    assert [d.windowTitle() for d in extracting] == ["Extract Pages"] * 2
    assert extracting[1].page_indexes() == [1]

    splitting = _opened(monkeypatch, dialogs.SplitDocumentDialog)
    window.act_split_pages.trigger()
    _entry(window.page_menu(1), "Split Document…").trigger()  # and on the page menu (E8)
    assert [d.windowTitle() for d in splitting] == ["Split Document"] * 2

    deleting = _opened(monkeypatch, dialogs.DeletePagesDialog)
    window.act_delete_page.trigger()
    _entry(window.page_menu(2), "Delete Pages…").trigger()
    assert [d.windowTitle() for d in deleting] == ["Delete Pages"] * 2
    assert deleting[1].page_indexes() == [2]
    assert len(window.document.pages) == 3                 # cancelled: nothing went

    cropping = _opened(monkeypatch, dialogs.CropPagesDialog)
    window.act_crop_page.trigger()
    assert window.act_crop_page.text() == "Crop Pages…"
    _entry(window.page_menu(1), "Crop Pages…").trigger()      # and on the page menu (E8)
    assert [d.windowTitle() for d in cropping] == ["Crop Pages"] * 2

    applying = _opened(monkeypatch, dialogs.ApplyToPagesDialog)
    window.apply_to_pages(_rect(window))
    assert [d.windowTitle() for d in applying] == ["Apply to Pages"]
    for seen in (blank, inserting, extracting, splitting, deleting, cropping, applying):
        for dialog in seen:
            dialog.deleteLater()


def test_dialogs_have_revus_fields(window):
    _pages(window, 3)
    blank = window.blank_page_dialog()
    assert blank.paper.itemText(0) == "Same as Current"
    assert blank.paper.findText("A3") > 0 and blank.paper.findText("Custom") > 0
    assert (blank.portrait.text(), blank.landscape.text()) == ("Portrait", "Landscape")
    assert [blank.placement.side.itemText(i) for i in range(2)] == ["Before", "After"]
    assert [b.text() for b in (blank.placement.first, blank.placement.last,
                               blank.placement.page)] == ["First Page", "Last Page", "Page:"]
    assert blank.go_button.text() == "OK"
    extract = window.extract_pages_dialog()
    assert [b.text() for b in (extract.delete_after, extract.separate, extract.use_labels,
                               extract.open_after)] == [
        "Delete Pages After Extracting", "Extract Pages as Separate Files",
        "Use Page Label to Name Files", "Open Files After Extraction"]
    crop = window.crop_pages_dialog()
    assert set(crop.margins) == {"top", "bottom", "left", "right"}
    assert crop.proportional.text() == "Set Proportional"
    assert crop.get_window.text() == "Get Window"
    apply = window.apply_to_pages_dialog()
    assert [b.text() for b in apply.buttons.values()] == [
        "All Pages", "Custom Range:", "Even Pages", "Odd Pages", "Landscape Pages",
        "Portrait Pages"]
    for dialog in (blank, extract, crop, apply):
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Insert Blank Page
# ---------------------------------------------------------------------------

def _blank(window, side, where, count=1, size="Same as Current", page=None,
           landscape=False):
    dialog = window.blank_page_dialog()
    dialog.paper.setCurrentText(size)
    dialog.page_count.setValue(count)
    (dialog.landscape if landscape else dialog.portrait).setChecked(True)
    dialog.placement.choose(where, side, page)
    target = window.finish_blank_page(dialog)
    dialog.deleteLater()
    return target


def test_insert_blank_page_before_the_first_page(window):
    _pages(window, 3)
    uids = [p.uid for p in window.document.pages]
    assert _blank(window, "before", "first", count=2, size="A3", landscape=True) == 0
    pages = window.document.pages
    assert len(pages) == 5 and [p.uid for p in pages[2:]] == uids
    assert all(p.setup.size_name == "A3" and p.setup.orientation == "landscape"
               for p in pages[:2])
    window.undo_stack.undo()                               # one undo step
    assert [p.uid for p in window.document.pages] == uids


def test_insert_blank_page_after_the_last_page(window):
    _pages(window, 3)
    assert _blank(window, "after", "last", count=3, size="A1") == 3
    pages = window.document.pages
    assert len(pages) == 6
    assert [p.setup.size_name for p in pages[3:]] == ["A1"] * 3
    assert pages[0].setup.size_name == "A4"


def test_insert_blank_page_before_page_n_custom_size(window):
    _pages(window, 3)
    dialog = window.blank_page_dialog()
    dialog.width_box.setValue(300)                         # typed: Custom
    dialog.height_box.setValue(400)
    assert dialog.paper.currentText() == "Custom"
    dialog.placement.choose("page", "before", 1)           # before page 2
    assert window.finish_blank_page(dialog) == 1
    dialog.deleteLater()
    page = window.document.pages[1]
    assert (page.setup.width_mm, page.setup.height_mm) == (300, 400)
    assert len(window.document.pages) == 4


def test_the_old_add_pages_name_still_works(window, monkeypatch):
    """What tests/test_september17_review.py pinned, through the new dialog."""
    window.interactive_prompts = True

    def choose(dialog):
        dialog.page_count.setValue(3)
        dialog.paper.setCurrentText("A3")
        dialog.landscape.setChecked(True)
        return QDialog.Accepted
    monkeypatch.setattr(dialogs.NewPagesDialog, "exec", choose)
    window.add_page()
    assert len(window.document.pages) == 4
    assert all(p.setup.size_name == "A3" and p.setup.orientation == "landscape"
               for p in window.document.pages[1:])


# ---------------------------------------------------------------------------
# Insert Pages
# ---------------------------------------------------------------------------

def test_insert_pages_places_the_chosen_pages(window, tmp_path):
    _pages(window, 2)
    source = _pdf(str(tmp_path / "three.pdf"), [(300, 400), (500, 300), (300, 400)])
    dialog = window.insert_pages_dialog()
    assert dialog.set_path(source)
    dialog.pages.setText("2-3")
    dialog.placement.choose("first", "before")
    window.finish_insert_pages(dialog)
    dialog.deleteLater()
    pages = window.document.pages
    assert len(pages) == 4
    assert [round(p.width_pt) for p in pages[:2]] == [500, 300]
    window.undo_stack.undo()
    assert len(window.document.pages) == 2


# ---------------------------------------------------------------------------
# Delete Pages
# ---------------------------------------------------------------------------

def test_delete_pages_deletes_the_chosen_pages_in_one_undo(window):
    _pages(window, 5)
    uids = [p.uid for p in window.document.pages]
    dialog = window.delete_pages_dialog()
    dialog.pages.set_custom("2, 4-5")
    assert window.finish_delete_pages(dialog) == 3
    dialog.deleteLater()
    assert [p.uid for p in window.document.pages] == [uids[0], uids[2]]
    window.undo_stack.undo()
    assert [p.uid for p in window.document.pages] == uids


def test_delete_pages_refuses_every_page(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    _pages(window, 3)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    dialog = window.delete_pages_dialog()
    dialog.pages.choose(PagesRange.ALL)
    assert "at least one page" in dialog.note.text()
    dialog.delete()                                        # OK: refused, still open
    assert warned and "at least one page" in warned[0]
    assert dialog.result() != QDialog.Accepted
    assert window.finish_delete_pages(dialog) == 0
    dialog.deleteLater()
    assert len(window.document.pages) == 3


def test_delete_pages_starts_on_the_run_picked_out(window):
    _pages(window, 5)
    _pick(window, [1, 2, 3])
    dialog = window.delete_pages_dialog(2)
    try:
        assert dialog.pages.which() == PagesRange.SELECTED
        assert dialog.pages.range.text() == "2-4"
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Extract Pages and Split Document
# ---------------------------------------------------------------------------

def test_extract_writes_the_chosen_pages(window, tmp_path):
    _pages(window, 4)
    dialog = window.extract_pages_dialog()
    dialog.pages.set_custom("1, 3-4")
    made = window.finish_extract_pages(dialog, str(tmp_path / "out.pdf"))
    dialog.deleteLater()
    assert made == [str(tmp_path / "out.pdf")]
    assert _count(made[0]) == 3
    assert len(window.document.pages) == 4                 # nothing deleted


def test_extract_as_separate_files_named_by_label_then_deleted(window, tmp_path):
    _pages(window, 4)
    window.document.pages[2].label = "A-101"
    window.document.pages[3].label = "A-102"
    uids = [p.uid for p in window.document.pages]
    dialog = window.extract_pages_dialog()
    dialog.pages.set_custom("3-4")
    dialog.separate.setChecked(True)
    dialog.use_labels.setChecked(True)
    dialog.delete_after.setChecked(True)
    made = window.finish_extract_pages(dialog, str(tmp_path / "sheets.pdf"))
    dialog.deleteLater()
    assert [os.path.basename(p) for p in made] == ["sheets A-101.pdf", "sheets A-102.pdf"]
    assert all(_count(p) == 1 for p in made)
    assert [p.uid for p in window.document.pages] == uids[:2]
    window.undo_stack.undo()                               # the delete, in one step
    assert len(window.document.pages) == 4


def test_extract_open_files_after_extraction(window, tmp_path):
    _pages(window, 2)
    dialog = window.extract_pages_dialog()
    dialog.pages.set_custom("2")
    dialog.open_after.setChecked(True)
    made = window.finish_extract_pages(dialog, str(tmp_path / "two.pdf"))
    dialog.deleteLater()
    assert window.document.path == made[0]                 # opened in a tab of its own
    assert len(window._open_documents) == 2


def test_split_makes_the_right_number_of_files(window, tmp_path):
    _pages(window, 5)
    dialog = window.split_document_dialog()
    dialog.page_count.setValue(2)
    dialog.folder.setText(str(tmp_path))
    dialog.suffix.setText("sheet")
    assert dialog.files() == 3
    made = window.finish_split(dialog)
    dialog.deleteLater()
    assert [os.path.basename(p) for p in made] == [
        "document sheet 1.pdf", "document sheet 2.pdf", "document sheet 3.pdf"]
    assert [_count(p) for p in made] == [2, 2, 1]


# ---------------------------------------------------------------------------
# Crop Pages
# ---------------------------------------------------------------------------

def test_crop_margins_go_on_the_chosen_pages(window):
    _pages(window, 3)
    before = [(p.width_pt, p.height_pt) for p in window.document.pages]
    rect = _rect(window, page=2, at=(100, 100))
    dialog = window.crop_pages_dialog()
    dialog.proportional.setChecked(True)
    dialog.margins["top"].setValue(10)                     # all four, proportional
    assert dialog.margins_mm() == {"top": 10, "bottom": 10, "left": 10, "right": 10}
    dialog.proportional.setChecked(False)
    dialog.margins["left"].setValue(20)
    dialog.pages.set_custom("1, 3")
    assert window.finish_crop_pages(dialog)
    dialog.deleteLater()
    pages = window.document.pages
    for which in (0, 2):
        width, height = before[which]
        assert pages[which].width_pt == pytest.approx(width - 30 * MM_TO_PT, abs=0.05)
        assert pages[which].height_pt == pytest.approx(height - 20 * MM_TO_PT, abs=0.05)
    assert (pages[1].width_pt, pages[1].height_pt) == before[1]
    moved = _rects(window, 2)[0]
    assert moved.pos().x() == pytest.approx(100 - 20 * MM_TO_PT, abs=0.05)
    window.undo_stack.undo()                               # one undo step
    assert [(p.width_pt, p.height_pt) for p in window.document.pages] == before
    assert rect is not None


def test_get_window_drags_and_comes_back_with_margins(window, monkeypatch):
    window.interactive_prompts = True
    _pages(window, 2)
    opened = []

    def first(self):
        opened.append(self.state())
        if len(opened) == 1:
            self.margins["top"].setValue(5)
            self.pages.choose(PagesRange.ALL)
            return dialogs.CropPagesDialog.PICK            # Get Window
        return QDialog.Rejected
    monkeypatch.setattr(dialogs.CropPagesDialog, "exec", first)
    window.act_crop_page.trigger()
    assert window.view.tool_key == "crop"
    frame = window.document.pages[0].frame
    width, height = frame.page_rect().width(), frame.page_rect().height()
    window.crop_page_region(frame, QRectF(10 * MM_TO_PT, 20 * MM_TO_PT,
                                          width - 40 * MM_TO_PT, height - 50 * MM_TO_PT))
    assert len(opened) == 2                                # back to the dialog
    margins = opened[1]["margins"]
    assert margins["left"] == pytest.approx(10, abs=0.01)
    assert margins["top"] == pytest.approx(20, abs=0.01)
    assert margins["right"] == pytest.approx(30, abs=0.01)
    assert margins["bottom"] == pytest.approx(30, abs=0.01)
    assert opened[1]["pages"] == PagesRange.ALL            # the rest as it was left
    assert (frame.page.width_pt, frame.page.height_pt) == (width, height)  # not cropped yet
    assert window.view.tool_key == "select"


def test_the_crop_tool_still_crops_by_dragging(window):
    frame = window.document.pages[0].frame
    assert window.crop_page_region(frame, QRectF(50, 50, 200, 300))
    assert (frame.page.width_pt, frame.page.height_pt) == pytest.approx((200, 300))


# ---------------------------------------------------------------------------
# Apply to Pages
# ---------------------------------------------------------------------------

def test_apply_to_even_and_odd_pages(window):
    _pages(window, 5)
    rect = _rect(window, page=0)
    dialog = window.apply_to_pages_dialog()
    dialog.choose(dialog.EVEN)
    assert window.finish_apply_to_pages(rect, dialog) == 2
    dialog.deleteLater()
    assert [len(_rects(window, i)) for i in range(5)] == [1, 1, 0, 1, 0]
    window.undo_stack.undo()
    assert [len(_rects(window, i)) for i in range(5)] == [1, 0, 0, 0, 0]
    rect = _rects(window, 0)[0]
    dialog = window.apply_to_pages_dialog()
    dialog.choose(dialog.ODD)                              # 3 and 5; 1 already has it
    assert dialog.page_indexes() == [2, 4]
    window.finish_apply_to_pages(rect, dialog)
    dialog.deleteLater()
    assert [len(_rects(window, i)) for i in range(5)] == [1, 0, 1, 0, 1]


def test_apply_to_pages_starts_on_the_thumbnail_selection(window):
    _pages(window, 4)
    _pick(window, [0, 2, 3])
    dialog = window.apply_to_pages_dialog()
    try:
        assert dialog.which() == dialog.CUSTOM
        assert dialog.range.text() == "3-4"
        assert dialog.page_indexes() == [2, 3]
    finally:
        dialog.deleteLater()


def test_apply_to_landscape_pages(window):
    _pages(window, 3)
    window.document.pages[2].setup.orientation = "landscape"
    rect = _rect(window, page=0)
    dialog = window.apply_to_pages_dialog()
    dialog.choose(dialog.LANDSCAPE)
    assert dialog.page_indexes() == [2]
    dialog.choose(dialog.PORTRAIT)
    assert dialog.page_indexes() == [1]
    dialog.deleteLater()
    assert rect is not None


# ---------------------------------------------------------------------------
# N1 titles, N2 Check Spelling, N3 Action, N7 Rename Page Label
# ---------------------------------------------------------------------------

def test_dialog_titles_are_revus_in_title_case(window):
    from calcforge.core.document import PageSetup
    for dialog, title in (
            (dialogs.PageSetupDialog(PageSetup(), window), "Page Setup"),
            (dialogs.DocumentPropertiesDialog(window.document, window),
             "Document Properties"),
            (dialogs.CountSubjectDialog("Count", "circle", window), "Count Tool"),
            (dialogs.RectangleSizeDialog("1", "1", "m", window), "Rectangle Size"),
            (dialogs.ArrayDialog("m", False, window), "Multiply"),
            (dialogs.ToolbarDialog([], set(), window), "Customise Toolbars")):
        assert dialog.windowTitle() == title
        dialog.deleteLater()
    assert window.act_customise_toolbar.text() == "Customise Toolbars…"


def test_check_spelling_has_revus_buttons(window):
    dialog = dialogs.SpellingDialog("teh", "of teh beam", 3, ["the"], window)
    try:
        assert dialog.windowTitle() == "Check Spelling"
        assert [b.text() for b in dialog.buttons.values()] == [
            "Ignore Once", "Ignore All", "Add to Dictionary", "Change", "Change All",
            "Close"]
    finally:
        dialog.deleteLater()


def _spell(window, monkeypatch, answers):
    from calcforge.items.text import TextItem
    frame = window.document.pages[0].frame
    box = TextItem("", QRectF(0, 0, 300, 40))
    frame.add_markup(box, QPointF(100, 100))
    box.set_text("teh one, teh two, teh three")
    asked = []

    class Answer(dialogs.SpellingDialog):
        def exec(self):
            asked.append(self)
            choice = answers.pop(0)
            self.edit.setText("the")
            self.choice = choice
            return 0 if choice == "stop" else 1
    monkeypatch.setattr(dialogs, "SpellingDialog", Answer)
    window.interactive_prompts = True
    changed = window.check_spelling()
    return box, changed, asked


def test_change_all_changes_every_one(window, monkeypatch):
    box, changed, asked = _spell(window, monkeypatch, ["change_all"])
    assert changed == 3 and len(asked) == 1
    assert box.doc.toPlainText() == "the one, the two, the three"


def test_ignore_once_asks_again_and_ignore_all_does_not(window, monkeypatch):
    box, changed, asked = _spell(window, monkeypatch, ["ignore_once", "ignore_all"])
    assert changed == 0 and len(asked) == 2
    assert box.doc.toPlainText() == "teh one, teh two, teh three"


def test_hyperlink_opens_revus_action_dialog(window):
    from calcforge.items.link import FILE, PAGE, VIEW, WEB, LinkItem
    dialog = dialogs.LinkDialog(LinkItem(QRectF(0, 0, 40, 20)), 3, (0, 0.0), window)
    try:
        assert dialog.windowTitle() == "Action"
        assert [(dialog.kind.itemText(i), dialog.kind.itemData(i))
                for i in range(dialog.kind.count())] == [
            ("Jump to Page", PAGE), ("Snapshot View", VIEW), ("Open File", FILE),
            ("Open URL", WEB)]
        dialog.kind.setCurrentIndex(dialog.kind.findData(WEB))
        assert dialog.address.isVisibleTo(dialog) and not dialog.page.isVisibleTo(dialog)
        dialog.address.setText("https://example.com")
        dialog.apply()
        assert dialog.item.kind == WEB and dialog.item.address == "https://example.com"
    finally:
        dialog.deleteLater()


def test_rename_page_label_edits_in_place(window):
    window.show()
    _pages(window, 2)
    QApplication.processEvents()
    _entry(window.page_menu(1), "Rename Page Label").trigger()
    editor = window.pages_panel.label_editor
    assert editor is not None and editor.parent() is window.pages_panel.list.viewport()
    assert editor.text() == "2"
    editor.setText("S-201")
    QTest.keyClick(editor, Qt.Key_Return)
    assert window.document.pages[1].label == "S-201"
    assert "S-201" in window.pages_panel.list.item(1).text()
    window.undo_stack.undo()
    assert window.document.pages[1].label == ""


def test_f2_on_a_thumbnail_and_escape_leaves_it(window):
    window.show()
    _pages(window, 2)
    QApplication.processEvents()
    listing = window.pages_panel.list
    listing.setFocus()
    listing.setCurrentRow(0)
    QTest.keyClick(listing, Qt.Key_F2)
    editor = window.pages_panel.label_editor
    assert editor is not None
    QTest.keyClicks(editor, "Plan")
    QTest.keyClick(editor, Qt.Key_Escape)
    assert window.pages_panel.label_editor is None
    assert window.document.pages[0].label == ""
