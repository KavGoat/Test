from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication


def _double_click(widget):
    point = QPointF(widget.rect().center())
    QApplication.sendEvent(widget, QMouseEvent(
        QEvent.MouseButtonDblClick, point, widget.mapToGlobal(point),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    QApplication.processEvents()


def test_double_clicking_the_markups_lists_handle_hides_and_shows_it(window):
    window.show()
    QApplication.processEvents()
    handle = window.bottom_split.handle(1)
    assert not window.markups_list_open()
    _double_click(handle)
    assert window.markups_list_open()
    height = window.bottom_split.sizes()[1]
    _double_click(handle)
    assert not window.markups_list_open()
    _double_click(handle)
    assert window.markups_list_open()
    assert abs(window.bottom_split.sizes()[1] - height) <= 2, "it comes back at its height"
