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
