"""A text box as a bookmark, and fields in a text box (the user, 2026-10-15:
"right click on text box ... make it an automatic bookmark with title of the
text inside. And if I move it to another page it refers to that page. Also
add right click on text box to select variable (and allow page number or date
or some property)")."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF

from calcforge.items.fields import expand, shown_text
from calcforge.items.text import TextItem


def _box(window, text, page=0, at=QPointF(100, 100)):
    item = TextItem(text, QRectF(0, 0, 200, 40))
    window.scene.frames[page].add_markup(item, at)
    return item


def test_a_text_box_bookmark_follows_its_box_to_another_page(window):
    window.add_page()
    item = _box(window, "Section 3 — Loads\nmore words")
    window.set_text_bookmark(item, True)
    marks = [m for m in window.document.bookmarks if m.markup == item.uid]
    assert len(marks) == 1 and marks[0].title == "Section 3 — Loads"
    assert marks[0].page_uid == window.document.pages[0].uid
    # moved to page 2: the bookmark goes with it
    second = window.scene.frames[1]
    item.setParentItem(second)
    item.setPos(50, 300)
    window.refresh_lists()
    (mark,) = [m for m in window.document.bookmarks if m.markup == item.uid]
    assert mark.page_uid == window.document.pages[1].uid and mark.y == 300
    # retitled with its words
    item.set_text("Section 4 — Wind")
    window.refresh_lists()
    assert mark.title == "Section 4 — Wind"
    # kept in the file, and gone with the box
    data = item.serialize()
    assert data.get("bookmark") is True
    second.remove_markup(item)
    window.refresh_lists()
    assert not [m for m in window.document.bookmarks if m.markup]


def test_fields_show_their_values_and_the_codes_while_typing(window):
    window.add_page()
    window.document.title = "Bridge 7"
    item = _box(window, "Sheet {page} of {pages} — {title}", page=1)
    assert shown_text(item) == "Sheet 2 of 2 — Bridge 7"
    assert item.text() == "Sheet {page} of {pages} — {title}", "the codes are what is kept"
    assert expand("{date:YYYY-MM-DD}", window.document, 0)[:2] == "20"


def test_a_variable_field_follows_its_equation(window):
    from tests.test_calc_panels import an_equation
    window.show()
    an_equation(window, "span:6.5", 100, 400)
    window.view.calc.leave()
    window.toggle_calc_mode(False)
    assert "span" in window.variable_names()
    item = _box(window, "")
    window.insert_text_field(item, "{=span}")
    assert item.text() == "{=span}"
    assert shown_text(item).startswith("6.5")
    assert expand("{=nothing}", window.document, 0) == "?"


def test_the_right_click_menu_offers_both(window):
    item = _box(window, "Notes")
    window.scene.clearSelection()
    item.setSelected(True)
    menu = window.build_context_menu(item, item.sceneBoundingRect().center())
    texts = [a.text() for a in menu.actions()]
    assert "Bookmark" in texts
    fields = next(a.menu() for a in menu.actions() if a.text() == "Insert Field")
    labels = [a.text() for a in fields.actions()]
    assert "Variable" in labels and "Page number" in labels


def test_the_properties_panel_has_the_bookmark_box(window):
    from PySide6.QtWidgets import QCheckBox
    item = _box(window, "Panel bookmark")
    window.scene.clearSelection()
    item.setSelected(True)
    window.refresh_selection()
    tick = window.properties_panel.findChild(QCheckBox, "markupBookmark")
    assert tick is not None and not tick.isChecked()
    tick.setChecked(True)
    assert item.auto_bookmark
    assert any(m.markup == item.uid for m in window.document.bookmarks)
