"""Dragging pages in the Pages panel (the user, 2026-10-05: "dragging a page
to rearrange led to a red cross for the cursor and actually visualised the
whole page which made it hard to see where I was dragging to. Just do a small
white shaded box")."""
from __future__ import annotations


def _labelled(window, count=5):
    for _ in range(count - 1):
        window.add_page()
    for number, page in enumerate(window.document.pages):
        page.label = f"P{number + 1}"
    window.rebuild_scenes()
    return window.pages_panel


def _order(window):
    return [page.label for page in window.document.pages]


def test_a_dragged_page_lands_where_the_line_was(window):
    panel = _labelled(window)
    panel.move_rows([3], 0)                    # the fourth, to the front
    assert _order(window) == ["P4", "P1", "P2", "P3", "P5"]
    panel.move_rows([0], 5)                    # the first, to the end
    assert _order(window) == ["P1", "P2", "P3", "P5", "P4"]


def test_a_run_of_pages_moves_together(window):
    panel = _labelled(window)
    panel.move_rows([1, 2], 5)
    assert _order(window) == ["P1", "P4", "P5", "P2", "P3"]
    panel.move_rows([3, 4], 3)                 # dropped where they are
    assert _order(window) == ["P1", "P4", "P5", "P2", "P3"]


def test_pages_picked_here_and_there_gather_where_they_are_dropped(window):
    panel = _labelled(window)
    panel.move_rows([0, 2, 4], 2)
    assert _order(window) == ["P2", "P1", "P3", "P5", "P4"]


def test_the_drag_shows_a_small_sheet_not_the_page(qapp):
    from calcforge.ui.panels import PageListWidget
    one = PageListWidget._drag_picture(1)
    several = PageListWidget._drag_picture(4)
    assert one.width() <= 40 and one.height() <= 46
    assert several.width() <= 44 and several.height() <= 50
    image = one.toImage()
    middle = image.pixelColor(one.width() // 2, one.height() // 2 + 8)
    assert middle.alpha() > 150 and middle.lightness() > 230, "white, a little see-through"
    corner = image.pixelColor(0, 0)
    assert corner.alpha() == 0


def test_dragging_pages_along_the_strip_is_allowed(window, qapp):
    """Over the strip a page drag is a move — not Qt's no-entry cross."""
    from PySide6.QtCore import QMimeData, QPointF, Qt, QByteArray
    from PySide6.QtGui import QDragMoveEvent
    from calcforge.ui.panels import PageListWidget
    panel = _labelled(window, 3)
    data = QMimeData()
    data.setData(PageListWidget.PAGES_MIME, QByteArray(b"0"))
    box = panel.list.visualItemRect(panel.list.item(2))
    event = QDragMoveEvent(box.center(), Qt.MoveAction, data, Qt.LeftButton, Qt.NoModifier)
    event.source = lambda: panel.list
    panel._drag_move(event)
    assert event.isAccepted() and event.dropAction() == Qt.MoveAction
    assert panel.list.external_drop_row is not None, "the line shows where it lands"
