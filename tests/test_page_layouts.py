"""Revu's page layouts (View menu, the user's choice 2026-10-15): Single
Page, Continuous, Side-by-Side and Continuous Side-by-Side, with Show Cover
Page in Side-by-Side. Only the screen changes; the document does not."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication


def _pages(window, count=5):
    for _ in range(count - 1):
        window.add_page()
    window.view.set_zoom(0.5)
    window.go_to_page(0)


def _row_of(frame):
    return round(frame.mapRectToScene(frame.page_rect()).top())


def _wheel(view, notches):
    point = view.viewport().rect().center()
    event = QWheelEvent(QPointF(point), QPointF(view.viewport().mapToGlobal(point)),
                        QPoint(), QPoint(0, notches), Qt.NoButton, Qt.NoModifier,
                        Qt.NoScrollPhase, False)
    QApplication.sendEvent(view.viewport(), event)


def test_side_by_side_puts_odd_pages_left_and_even_right(window):
    _pages(window)
    window.act_layout_continuous_side.trigger()
    frames = window.scene.frames
    assert window.status_scroll.text() == "Continuous Side-by-Side"
    assert all(frame.isVisible() for frame in frames)
    assert _row_of(frames[0]) == _row_of(frames[1]) < _row_of(frames[2]) == _row_of(frames[3])
    assert frames[0].pos().x() < frames[1].pos().x()
    assert _row_of(frames[4]) > _row_of(frames[3])            # the fifth, alone
    assert len(window.document.pages) == 5, "the document is untouched"


def test_a_cover_page_stands_alone(window):
    _pages(window, 4)
    window.act_layout_continuous_side.trigger()
    window.act_cover_page.trigger()
    frames = window.scene.frames
    assert _row_of(frames[0]) < _row_of(frames[1]) == _row_of(frames[2]) < _row_of(frames[3])


def test_single_page_shows_one_page_and_the_wheel_turns_at_its_end(window):
    _pages(window, 3)
    window.show()
    window.act_layout_single.trigger()
    frames = window.scene.frames
    assert [frame.isVisible() for frame in frames] == [True, False, False]
    for _ in range(40):                      # scroll down the page, then over its end
        _wheel(window.view, -120)
        if window.current_index == 1:
            break
    assert window.current_index == 1
    assert [frame.isVisible() for frame in frames] == [False, True, False]
    window.go_to_page(2)
    assert [frame.isVisible() for frame in frames] == [False, False, True]
    window.act_layout_continuous.trigger()
    assert all(frame.isVisible() for frame in frames)


def test_side_by_side_shows_one_spread_at_a_time(window):
    _pages(window, 4)
    window.act_layout_side.trigger()
    frames = window.scene.frames
    assert [frame.isVisible() for frame in frames] == [True, True, False, False]
    window.go_to_page(3)
    assert [frame.isVisible() for frame in frames] == [False, False, True, True]
    assert window.scene.frame_at(frames[2].mapRectToScene(frames[2].page_rect()).center()) is frames[2]


def test_each_document_keeps_its_own_layout(window):
    _pages(window, 2)
    window.act_layout_side.trigger()
    window.act_new_tab.trigger()
    assert len(window._open_documents) == 2
    assert window.status_scroll.text() == "Continuous"
    window.switch_to_document(0)
    assert window.status_scroll.text() == "Side-by-Side"
    assert window.act_layout_side.isChecked()
