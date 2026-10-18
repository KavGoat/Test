"""The Markups List's bar, as Revu's (the user, 2026-10-18): Revu's blue under
the pointer, a click opens or closes the list, a drag still sizes it, and a
double-click is two clicks, so it ends where it started."""
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def settle(ms=60):
    timer = QTimer()
    timer.setSingleShot(True)
    timer.start(ms)
    while timer.isActive():
        QApplication.instance().processEvents()


def handle_of(window):
    return window.bottom_split.handle(1)


def click(widget, at=None):
    at = at or widget.rect().center()
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, at)
    settle()


def test_a_click_on_the_markups_lists_bar_opens_and_closes_it(window):
    window.show()
    settle()
    assert not window.markups_list_open()
    click(handle_of(window))
    assert window.markups_list_open()
    height = window.bottom_split.sizes()[1]
    settle(QApplication.doubleClickInterval() + 50)      # two clicks, not a double-click
    click(handle_of(window))
    assert not window.markups_list_open()
    settle(QApplication.doubleClickInterval() + 50)
    click(handle_of(window))
    assert window.markups_list_open()
    assert abs(window.bottom_split.sizes()[1] - height) <= 2, "it comes back at its height"


def double_click_at(widget, at):
    """A double-click as the system sends one: press, release, then the
    second press as a double-click, then its release — each to whatever is
    under that spot of the screen by then (the bar moves with the list)."""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    spot = widget.mapToGlobal(at)
    QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, at)
    QTest.mouseRelease(widget, Qt.LeftButton, Qt.NoModifier, at)
    settle(20)
    under = QApplication.widgetAt(spot) or widget.window()
    local = QPointF(under.mapFromGlobal(spot))
    for kind, buttons in ((QEvent.MouseButtonDblClick, Qt.LeftButton),
                          (QEvent.MouseButtonRelease, Qt.NoButton)):
        QApplication.sendEvent(under, QMouseEvent(kind, local, QPointF(spot), Qt.LeftButton,
                                                  buttons, Qt.NoModifier))
    settle()


def test_a_double_click_ends_where_it_started(window):
    window.show()
    settle()
    assert not window.markups_list_open()
    double_click_at(handle_of(window), handle_of(window).rect().center())
    assert not window.markups_list_open()           # opened, and closed again
    settle(QApplication.doubleClickInterval() + 50)
    click(handle_of(window))
    assert window.markups_list_open()
    settle(QApplication.doubleClickInterval() + 50)
    double_click_at(handle_of(window), handle_of(window).rect().center())
    assert window.markups_list_open()               # closed, and opened again


def test_dragging_the_bar_sizes_the_list_and_does_not_toggle_it(window):
    window.show()
    settle()
    click(handle_of(window))
    assert window.markups_list_open()
    height = window.bottom_split.sizes()[1]
    handle = handle_of(window)
    at = handle.rect().center()
    QTest.mousePress(handle, Qt.LeftButton, Qt.NoModifier, at)
    for step in range(1, 7):
        QTest.mouseMove(handle, at - QPoint(0, 10 * step))
        settle(20)
    QTest.mouseRelease(handle, Qt.LeftButton, Qt.NoModifier, at - QPoint(0, 60))
    settle()
    assert window.markups_list_open()                    # still open: a drag, not a click
    assert window.bottom_split.sizes()[1] >= height + 40


def test_the_bar_is_blue_under_the_pointer(window):
    from calcforge.ui.docks import accent_colour
    window.show()
    settle()
    handle = handle_of(window)
    QTest.mouseMove(window.view.viewport(), window.view.viewport().rect().center())
    settle()
    resting = handle.grab().toImage().pixelColor(handle.width() // 2, handle.height() // 2)
    QTest.mouseMove(handle, handle.rect().center())
    settle()
    assert handle.underMouse()
    hover = handle.grab().toImage().pixelColor(handle.width() // 2, handle.height() // 2)
    assert hover.name() == accent_colour().name(), (hover.name(), resting.name())
    assert resting.name() != hover.name()
