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


def _wheel(view, notches, modifiers=None):
    """A turn of the wheel; by default the one that scrolls (Ctrl with the
    wheel zooming, as it does out of the box)."""
    from calcforge.ui import preferences

    if modifiers is None:
        modifiers = Qt.ControlModifier if preferences.current().wheel_zooms() \
            else Qt.NoModifier
    point = view.viewport().rect().center()
    event = QWheelEvent(QPointF(point), QPointF(view.viewport().mapToGlobal(point)),
                        QPoint(), QPoint(0, notches), Qt.NoButton, modifiers,
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


# -- the wheel in Single Page, as Revu (the user, 2026-10-19), and Preferences --

def _single(window, pages=3):
    _pages(window, pages)
    window.resize(1000, 760)
    window.show()
    QApplication.processEvents()
    window.act_layout_single.trigger()
    return window.view


def test_single_page_the_plain_wheel_zooms_as_in_continuous(window):
    """Revu: the wheel does in Single Page what it does in Continuous."""
    view = _single(window)
    before = view.zoom()
    _wheel(view, 120, Qt.NoModifier)
    assert view.zoom() > before, "the plain wheel zooms"
    assert window.current_index == 0


def test_single_page_zoomed_in_scrolls_within_the_page_then_turns(window):
    view = _single(window)
    view.set_zoom(view.zoom() * 3)
    window.go_to_page(0)
    view.go_to_page_top(0)
    frames = window.scene.frames
    bar = view.verticalScrollBar()
    top = bar.value()
    _wheel(view, -120)
    assert window.current_index == 0, "inside the page, the wheel moves within it"
    assert bar.value() == top + 30, "by a notch, at once"
    # on down to the foot of the page, then over its end onto the next
    for _ in range(400):
        _wheel(view, -120)
        if window.current_index == 1:
            break
    assert window.current_index == 1
    assert [frame.isVisible() for frame in frames] == [False, True, False]
    # and up again: over the top of this page lands at the foot of the last
    for _ in range(400):
        _wheel(view, 120)
        if window.current_index == 0:
            break
    assert window.current_index == 0
    assert bar.value() == bar.maximum(), "back at the foot of the page before"


def test_single_page_zoomed_out_shows_one_page_only(window):
    view = _single(window)
    for _ in range(25):
        _wheel(view, -120, Qt.NoModifier)            # right out
    frames = window.scene.frames
    assert view.zoom() < 0.2
    assert [frame.isVisible() for frame in frames] == [True, False, False]
    shown = view.mapToScene(view.viewport().rect()).boundingRect()
    page = frames[0].mapRectToScene(frames[0].page_rect())
    assert shown.contains(page), "the whole page is in view, and only it"
    grab = view.viewport().grab()
    assert not grab.isNull()


def test_preferences_page_end_stays_on_the_page(window):
    from calcforge.ui import preferences

    preferences.current().page_end = preferences.PAGE_END_STAY
    view = _single(window)
    for _ in range(60):
        _wheel(view, -120)
    assert window.current_index == 0, "scrolling past the end stays on the page"
    window.act_next_page.trigger()
    assert window.current_index == 1, "turning the page by other means still works"


def test_preferences_page_wheel_always_scrolls(window):
    """The old way, kept as a choice: in Single Page the plain wheel scrolls
    and turns pages, and Ctrl zooms."""
    from calcforge.ui import preferences

    preferences.current().page_wheel = preferences.PAGE_WHEEL_SCROLL
    view = _single(window)
    before = view.zoom()
    _wheel(view, -120, Qt.NoModifier)
    assert window.current_index == 1 and view.zoom() == before
    _wheel(view, 120, Qt.ControlModifier)
    assert view.zoom() > before
    window.act_layout_continuous.trigger()
    before = view.zoom()
    _wheel(view, 120, Qt.NoModifier)
    assert view.zoom() > before, "in Continuous the wheel still zooms"


def test_continuous_at_fit_page_scrolls_on_through_the_pages(window):
    """Revu: Fit Page in Continuous still scrolls page to page."""
    _pages(window, 3)
    window.resize(1000, 760)
    window.show()
    QApplication.processEvents()
    view = window.view
    view.fit_page()
    for _ in range(200):
        _wheel(view, -120)
        if window.current_index == 2:
            break
    assert window.current_index == 2
    assert all(frame.isVisible() for frame in window.scene.frames)


def test_side_by_side_scrolls_then_turns_a_spread(window):
    _pages(window, 4)
    window.resize(1000, 760)
    window.show()
    QApplication.processEvents()
    window.act_layout_side.trigger()
    frames = window.scene.frames
    for _ in range(200):
        _wheel(window.view, -120)
        if frames[2].isVisible():
            break
    assert [frame.isVisible() for frame in frames] == [False, False, True, True]


def test_the_wheel_preferences_are_in_the_dialog_and_persist(window):
    from calcforge.ui import preferences
    from calcforge.ui.dialogs import PreferencesDialog

    prefs = preferences.Preferences()
    assert prefs.page_wheel == preferences.PAGE_WHEEL_AS_WHEEL
    assert prefs.page_end == preferences.PAGE_END_TURN
    assert prefs.smooth_wheel is False
    dialog = PreferencesDialog(prefs, window)
    assert dialog.page_wheel.currentData() == preferences.PAGE_WHEEL_AS_WHEEL
    assert dialog.page_end.currentData() == preferences.PAGE_END_TURN
    assert not dialog.smooth_wheel.isChecked()
    dialog.page_wheel.setCurrentIndex(dialog.page_wheel.findData(preferences.PAGE_WHEEL_SCROLL))
    dialog.page_end.setCurrentIndex(dialog.page_end.findData(preferences.PAGE_END_STAY))
    dialog.smooth_wheel.setChecked(True)
    preferences.apply(dialog.result_preferences())
    preferences.forget()
    again = preferences.current()
    assert again.page_wheel == preferences.PAGE_WHEEL_SCROLL
    assert again.page_end == preferences.PAGE_END_STAY
    assert again.smooth_wheel is True
    dialog = PreferencesDialog(again, window)
    assert dialog.page_wheel.currentData() == preferences.PAGE_WHEEL_SCROLL
    assert dialog.page_end.currentData() == preferences.PAGE_END_STAY
    assert dialog.smooth_wheel.isChecked()
