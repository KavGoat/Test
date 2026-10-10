"""Found using the app on 2026-10-10: Properties kept showing a markup
after Escape had let it go (editing it there changed a markup nobody had
picked), and a blank page's thumbnail was white on the white list."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QLabel

from calcforge.items.shapes import RectItem
from tests.test_tables import pump, w  # noqa: F401


def visible_labels(w):
    return [label.text() for label in w.properties_panel.findChildren(QLabel) if label.isVisible()]


def test_properties_let_go_when_escape_does(w):
    box = RectItem()
    box.set_local_rect(QRectF(0, 0, 40, 20))
    w.document.pages[0].frame.add_markup(box, QPointF(100, 100))
    box.setSelected(True)
    w.refresh_selection()
    pump()
    assert "Rectangle" in visible_labels(w)
    w.view.escape_everything()
    pump()
    pump()
    assert "Rectangle" not in visible_labels(w)
    assert any(text.startswith("Nothing selected") for text in visible_labels(w))
    box.setSelected(True)                  # picked some other way than a click
    pump()
    pump()
    assert "Rectangle" in visible_labels(w)


def test_a_blank_pages_thumbnail_has_an_edge(w):
    w.add_page()
    pump()
    entry = w.pages_panel.list.item(1)
    icon = entry.icon()
    image = icon.pixmap(icon.availableSizes()[0]).toImage()
    corner, middle = image.pixelColor(0, image.height() // 2), image.pixelColor(image.width() // 2,
                                                                               image.height() // 2)
    assert middle.name() == "#ffffff" and corner.name() != "#ffffff", "white page, grey edge"


def test_new_markups_are_signed_with_the_persons_name(w, tmp_path, monkeypatch):
    """Answered 2026-10-10: as Bluebeam, a new markup carries the login name
    as its author (Preferences can change it), and the saved PDF says so."""
    import pymupdf

    from calcforge.ui import preferences
    from tests.test_tables import page_to_scene
    from tests.test_usability import drag
    prefs = preferences.current()
    monkeypatch.setattr(prefs, "author", "J. Engineer")
    w.select_tool("rect")
    a, b = page_to_scene(w, 80, 100), page_to_scene(w, 200, 140)
    w.view.centerOn(a)
    drag(w.view, a.x(), a.y(), b.x(), b.y())
    pump()
    (box,) = [i for i in w.document.pages[0].frame.markups() if isinstance(i, RectItem)]
    assert box.author == "J. Engineer"
    path = str(tmp_path / "signed.pdf")
    w.document.path = path
    assert w.save_document()
    with pymupdf.open(path) as pdf:
        authors = [annot.info.get("title") for annot in pdf[0].annots()]
    assert "J. Engineer" in authors


def test_the_author_preference_starts_as_the_login_name():
    from calcforge.ui.preferences import Preferences, login_name
    assert Preferences().author == login_name() != ""
