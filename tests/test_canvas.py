"""The canvas: one continuous scroll through every page of the document.

A calculation sheet is read the way a PDF is read, so the pages are stacked
down one canvas rather than shown one at a time. These tests hold that
arrangement to what a reader expects: the pages are in order with a gap
between them, scrolling past a boundary changes which page you are on,
drawing lands on the page under the pointer, and a markup dragged onto the
next page belongs to that page afterwards.
"""
import pytest
from PySide6.QtCore import QPointF, Qt

from calcforge.items.shapes import RectItem
from calcforge.ui.scene import PAGE_GAP, DocumentScene, PageFrame

from tests.test_usability import click, drag, markups, on_page, only


def frames(window):
    return window.view.scene().frames


# ---------------------------------------------------------------------------
# the arrangement
# ---------------------------------------------------------------------------

def test_every_page_is_on_the_one_canvas(window):
    window.add_page()
    window.add_page()
    scene = window.view.scene()
    assert isinstance(scene, DocumentScene)
    assert len(frames(window)) == 3
    assert all(isinstance(frame, PageFrame) for frame in frames(window))
    assert [frame.page for frame in frames(window)] == window.document.pages


def test_pages_are_stacked_in_order_with_a_gap_between_them(window):
    window.add_page()
    window.add_page()
    tops = [frame.pos().y() for frame in frames(window)]
    assert tops == sorted(tops)
    for first, second in zip(frames(window), frames(window)[1:]):
        gap = second.pos().y() - (first.pos().y() + first.page.height_pt)
        assert gap == pytest.approx(PAGE_GAP)


def test_pages_of_different_sizes_are_centred_on_each_other(window):
    window.add_page()
    window.document.pages[1].setup.apply_size("A3")
    window.rebuild_scenes()
    centres = [frame.pos().x() + frame.page.width_pt / 2 for frame in frames(window)]
    assert centres[0] == pytest.approx(centres[1])


def test_the_canvas_covers_every_page(window):
    window.add_page()
    window.add_page()
    rect = window.view.scene().sceneRect()
    for frame in frames(window):
        assert rect.contains(frame.mapRectToScene(frame.page_rect()))


def test_adding_a_page_re_lays_out_the_canvas(window):
    before = window.view.scene().sceneRect().height()
    window.add_page()
    after = window.view.scene().sceneRect().height()
    assert after > before + window.current_page().height_pt


# ---------------------------------------------------------------------------
# scrolling
# ---------------------------------------------------------------------------

def test_the_whole_document_can_be_scrolled_through(window):
    window.add_page()
    window.add_page()
    window.view.set_zoom(1.0)
    bar = window.view.verticalScrollBar()
    assert bar.maximum() > bar.minimum(), "there is nothing to scroll"


def test_scrolling_onto_another_page_makes_it_the_current_one(window):
    window.add_page()
    window.add_page()
    window.view.set_zoom(1.0)
    window.go_to_page(0)
    assert window.current_index == 0

    third = frames(window)[2]
    window.view.centerOn(third.mapRectToScene(third.page_rect()).center())
    assert window.view.visible_page_index() == 2
    assert window.current_index == 2
    assert window.page_spin.value() == 3


def test_going_to_a_page_scrolls_to_it_rather_than_swapping_the_canvas(window):
    window.add_page()
    window.add_page()
    scene_before = window.view.scene()
    window.go_to_page(0)
    top = window.view.verticalScrollBar().value()
    window.go_to_page(2)
    assert window.view.scene() is scene_before        # same canvas throughout
    assert window.view.verticalScrollBar().value() > top
    assert window.view.visible_page_index() == 2


def test_the_page_under_a_point_is_the_one_it_lands_on(window):
    window.add_page()
    scene = window.view.scene()
    for index, frame in enumerate(frames(window)):
        centre = frame.mapRectToScene(frame.page_rect()).center()
        assert scene.index_at(centre) == index


# ---------------------------------------------------------------------------
# drawing on a continuous canvas
# ---------------------------------------------------------------------------

def test_drawing_lands_on_the_page_under_the_pointer(window):
    window.add_page()
    window.go_to_page(0)
    window.select_tool("rect")
    x0, y0 = on_page(window, 1, 80, 80)          # aim at the second page
    x1, y1 = on_page(window, 1, 200, 180)
    drag(window.view, x0, y0, x1, y1)

    assert window.document.pages[0].frame.markups() == []
    second = window.document.pages[1].frame.markups()
    assert len(second) == 1
    # …and its position is relative to its own page, as it is saved
    assert second[0].pos().x() == pytest.approx(80, abs=2)
    assert second[0].pos().y() == pytest.approx(80, abs=2)


def test_a_markup_dragged_onto_the_next_page_belongs_to_it(window):
    window.add_page()
    window.select_tool("rect")
    x0, y0 = on_page(window, 0, 100, 600)
    drag(window.view, x0, y0, *on_page(window, 0, 220, 700))
    window.select_tool("select")
    item = only(window, RectItem)[0]
    assert item.parentItem() is window.document.pages[0].frame

    centre = item.mapToScene(item.local_rect().center())
    target = on_page(window, 1, 160, 200)
    drag(window.view, centre.x(), centre.y(), *target)

    assert item.parentItem() is window.document.pages[1].frame
    assert window.document.pages[0].frame.markups() == []
    assert window.document.pages[1].frame.markups() == [item]
    # it stayed where it was dropped
    # the drag moved it by a delta, so it sits where it was dropped
    assert 100 < item.pos().y() < 260


def test_a_page_saves_only_what_is_on_it(window):
    window.add_page()
    for index in range(2):
        window.select_tool("rect")
        drag(window.view, *on_page(window, index, 60, 60),
             *on_page(window, index, 160, 160))
    window.select_tool("select")
    for index in range(2):
        data = window.document.pages[index].to_dict()["items"]
        assert len(data) == 1
        assert data[0]["x"] == pytest.approx(60, abs=2)
        assert data[0]["y"] == pytest.approx(60, abs=2)


def test_the_grid_belongs_to_the_page_not_the_canvas(window):
    """A snapped point lands on the page's own grid, whatever page it is."""
    window.document.settings.snap_to_grid = True
    window.document.settings.grid_mm = 5.0
    window.add_page()
    step = 5.0 * 72.0 / 25.4
    for index in range(2):
        frame = window.document.pages[index].frame
        rough = frame.mapToScene(QPointF(step * 3 + 2.0, step * 4 + 2.0))
        snapped = frame.mapFromScene(window.view.snap_scene(rough))
        assert snapped.x() == pytest.approx(step * 3)
        assert snapped.y() == pytest.approx(step * 4)


# ---------------------------------------------------------------------------
# how the paper reads
# ---------------------------------------------------------------------------

def test_the_desk_is_a_different_colour_from_the_paper(window):
    from calcforge.theme import CANVAS, LIGHT

    desk = window.view.scene().backgroundBrush().color()
    assert desk.name() == CANVAS[LIGHT]
    assert desk.name() != "#ffffff"
    # and dark enough to see a white sheet against
    assert desk.lightness() < 200


def test_a_page_is_drawn_with_an_edge_and_a_shadow(window):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    frame = window.current_page().frame
    scene = frame.scene()
    area = frame.mapRectToScene(frame.page_rect()).adjusted(-30, -30, 30, 30)
    image = QImage(300, 400, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, 300, 400), area)
    painter.end()

    columns = [image.pixelColor(x, 200).name() for x in range(300)]
    assert "#ffffff" in columns, "no paper"
    # Somewhere between the desk and the paper there is a darker edge line.
    paper_starts = columns.index("#ffffff")
    edge = columns[max(paper_starts - 3, 0):paper_starts]
    assert any(colour != columns[0] for colour in edge), "no page edge drawn"


def test_the_shadow_falls_outside_the_paper(window):
    frame = window.current_page().frame
    assert frame.boundingRect().right() > frame.page_rect().right()
    assert frame.boundingRect().bottom() > frame.page_rect().bottom()


# ---------------------------------------------------------------------------
# getting about, the way every reader does it
# ---------------------------------------------------------------------------

def wheel(view, dy, modifiers=Qt.NoModifier, at=None, pixels=False):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    position = at or QPointF(view.viewport().rect().center())
    angle = QPoint(0, 0) if pixels else QPoint(0, dy)
    pixel = QPoint(0, dy) if pixels else QPoint(0, 0)
    event = QWheelEvent(position, view.viewport().mapToGlobal(position.toPoint()),
                        pixel, angle, Qt.NoButton, modifiers,
                        Qt.NoScrollPhase, False)
    QApplication.sendEvent(view.viewport(), event)


def press(view, key, modifiers=Qt.NoModifier):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    QApplication.sendEvent(view, QKeyEvent(QEvent.KeyPress, key, modifiers, ""))


def _three_pages(window):
    window.add_page()
    window.add_page()
    window.view.set_zoom(1.0)
    window.go_to_page(0)


def test_the_wheel_scrolls_the_document(window):
    _three_pages(window)
    bar = window.view.verticalScrollBar()
    before = bar.value()
    wheel(window.view, -240)
    assert bar.value() > before


def test_shift_and_the_wheel_scroll_sideways(window):
    _three_pages(window)
    window.view.set_zoom(3.0)                 # wide enough to scroll across
    bar = window.view.horizontalScrollBar()
    before = bar.value()
    wheel(window.view, -240, Qt.ShiftModifier)
    assert bar.value() > before


def test_ctrl_and_the_wheel_zoom(window):
    _three_pages(window)
    before = window.view.zoom()
    wheel(window.view, 240, Qt.ControlModifier)
    assert window.view.zoom() > before
    wheel(window.view, -480, Qt.ControlModifier)
    assert window.view.zoom() < before


def test_a_trackpad_scrolls_smoothly(window):
    """Pixel deltas are honoured, so two fingers do not move in notches."""
    _three_pages(window)
    bar = window.view.verticalScrollBar()
    before = bar.value()
    wheel(window.view, -30, pixels=True)
    assert bar.value() == before + 30


def test_page_up_and_down_scroll_a_screenful(window):
    _three_pages(window)
    bar = window.view.verticalScrollBar()
    start = bar.value()
    press(window.view, Qt.Key_PageDown)
    assert bar.value() == min(start + bar.pageStep(), bar.maximum())
    press(window.view, Qt.Key_PageUp)
    assert bar.value() == start


def test_ctrl_home_and_end_reach_the_ends_of_the_document(window):
    _three_pages(window)
    bar = window.view.verticalScrollBar()
    press(window.view, Qt.Key_End, Qt.ControlModifier)
    assert bar.value() == bar.maximum()
    press(window.view, Qt.Key_Home, Qt.ControlModifier)
    assert bar.value() == bar.minimum()


def test_arrows_scroll_when_nothing_is_selected(window):
    _three_pages(window)
    bar = window.view.verticalScrollBar()
    before = bar.value()
    press(window.view, Qt.Key_Down)
    assert bar.value() > before


def test_arrows_still_nudge_a_selected_markup(window):
    _three_pages(window)
    window.select_tool("rect")
    drag(window.view, *on_page(window, 0, 100, 100), *on_page(window, 0, 200, 200))
    window.select_tool("select")
    item = only(window, RectItem)[0]
    item.setSelected(True)
    origin = item.pos()
    scroll = window.view.verticalScrollBar().value()
    press(window.view, Qt.Key_Down)
    assert item.pos().y() > origin.y()
    assert window.view.verticalScrollBar().value() == scroll


def test_ctrl_page_down_goes_to_the_next_page(window):
    _three_pages(window)
    window.act_next_page.trigger()
    assert window.current_index == 1
    window.act_prev_page.trigger()
    assert window.current_index == 0


def test_zoom_stays_within_its_limits(window):
    from calcforge.ui.view import MAX_ZOOM, MIN_ZOOM

    for _ in range(60):
        window.view.zoom_in()
    assert window.view.zoom() == pytest.approx(MAX_ZOOM)
    for _ in range(120):
        window.view.zoom_out()
    assert window.view.zoom() == pytest.approx(MIN_ZOOM)


def test_fit_page_fits_the_page_being_looked_at(window):
    _three_pages(window)
    window.go_to_page(2)
    window.view.fit_page()
    frame = window.document.pages[2].frame
    rect = frame.mapRectToScene(frame.page_rect())
    visible = window.view.mapToScene(window.view.viewport().rect()).boundingRect()
    assert visible.contains(rect.center())
    assert visible.height() >= rect.height() - 1


def test_actual_size_is_one_to_one(window):
    window.view.set_zoom(0.4)
    window.act_actual_size.trigger()
    assert window.view.zoom() == pytest.approx(1.0)
