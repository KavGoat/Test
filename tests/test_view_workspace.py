"""Revu's View menu workspace (the user's choices, 2026-10-15): rulers, the
Full-Screen Crosshair and the Dimmer."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from calcforge.ui import scene as scene_module


def _render(window, rect):
    image = QImage(int(rect.width()), int(rect.height()), QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    window.scene.render(painter, QRectF(image.rect()), rect)
    painter.end()
    return image


def test_the_dimmer_tones_down_the_content_but_not_the_markups(window, monkeypatch):
    from calcforge.items.shapes import RectItem
    frame = window.scene.frames[0]
    monkeypatch.setattr(type(frame), "paint_the_pdf",
                        lambda self, painter, *_a, **_k: painter.fillRect(
                            QRectF(0, 0, 100, 100), QColor("#000000")))
    window.view.scene().clearSelection()
    box = RectItem("rect", QRectF(0, 0, 40, 40))
    box.style.fill = "#000000"
    box.style.fill_opacity = 1.0
    frame.add_markup(box) if hasattr(frame, "add_markup") else box.setParentItem(frame)
    box.setPos(60, 60)
    area = frame.mapRectToScene(QRectF(0, 0, 100, 100))
    try:
        assert QColor(_render(window, area).pixel(20, 20)).lightness() < 10
        window.act_dim_content.trigger()                 # Ctrl+F5, at Revu's 40 %
        assert scene_module.DIMMER["on"]
        dimmed = QColor(_render(window, area).pixel(20, 20)).lightness()
        assert 140 < dimmed < 165, dimmed                 # content at 40 %
        assert QColor(_render(window, area).pixel(80, 80)).lightness() < 10, "markups stay"
        level = next(a for a in window.dimmer_levels.actions() if a.data() == 80)
        level.trigger()
        assert QColor(_render(window, area).pixel(20, 20)).lightness() < 60
        assert not frame.print_mode
    finally:
        window.act_dim_content.setChecked(False)
        scene_module.DIMMER["level"] = 0.4
    assert not scene_module.DIMMER["on"]


def test_rulers_measure_from_the_page_corner_in_the_chosen_units(window):
    window.show()
    window.act_rulers.trigger()
    rulers = window.view.rulers
    QApplication.processEvents()
    assert rulers.top.isVisible() and rulers.left.isVisible()
    assert window.view.viewport().geometry().top() >= 20, "the drawing moves aside for them"
    page = rulers.page_rect()
    corner = rulers.top._along(page.topLeft())
    # one centimetre further along the top is 72/2.54 points at the zoom
    one_cm = rulers.top._along(page.topLeft() + QPointF(72 / 2.54, 0)) - corner
    assert abs(one_cm - 72 / 2.54 * window.view.zoom()) < 0.6
    rulers.set_unit("in")
    assert rulers.unit == "in"
    window.view.cursorMoved.emit(page.topLeft() + QPointF(36, 36))
    assert rulers.pointer == page.topLeft() + QPointF(36, 36)
    rulers.top.grab()                                    # paints without error
    rulers.left.grab()
    window.act_rulers.trigger()
    assert not rulers.top.isVisible()
    assert window.view.viewport().geometry().top() < 20
    rulers.set_unit("cm")


def test_the_full_screen_crosshair_meets_at_the_pointer(window):
    window.show()
    window.act_crosshair.trigger()
    cross = window.view.crosshair
    page = window.view.rulers.page_rect()
    point = page.center()
    window.view.cursorMoved.emit(point)
    assert cross.at == QPointF(window.view.mapFromScene(point))
    image = window.view.viewport().grab().toImage()
    x, y = int(cross.at.x()), int(cross.at.y())
    blue = QColor("#1971c2")
    assert QColor(image.pixel(x, 5)) == blue and QColor(image.pixel(5, y)) == blue
    window.act_crosshair.trigger()
    assert not cross.on


def _key(widget, key):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    QApplication.sendEvent(widget, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))


def test_presentation_shows_the_page_alone_and_esc_puts_everything_back(window):
    window.add_page()
    window.add_page()
    window.go_to_page(0)
    window.show()
    QApplication.processEvents()
    toolbars_before = [bar.isVisible() for bar in window.toolbars]
    window.act_presentation.trigger()
    QApplication.processEvents()
    assert window.isFullScreen()
    assert not window.menuBar().isVisible() and not window.statusBar().isVisible()
    assert not any(bar.isVisible() for bar in window.toolbars)
    assert window.scene.page_mode == "single"
    _key(window.view, Qt.Key_Right)
    assert window.current_index == 1
    _key(window.view, Qt.Key_Space)
    assert window.current_index == 2
    _key(window.view, Qt.Key_Left)
    assert window.current_index == 1
    _key(window.view, Qt.Key_Escape)
    QApplication.processEvents()
    assert not window.act_presentation.isChecked()
    assert window.menuBar().isVisible() and window.statusBar().isVisible()
    assert [bar.isVisible() for bar in window.toolbars] == toolbars_before
    assert window.scene.page_mode == "continuous"
    assert not window.isFullScreen()


def test_full_screen_comes_and_goes(window):
    window.show()
    window.act_full_screen.trigger()
    QApplication.processEvents()
    assert window.isFullScreen()
    window.act_full_screen.trigger()
    QApplication.processEvents()
    assert not window.isFullScreen()


def test_undo_history_lists_what_was_done_and_goes_back_to_any_of_it(window):
    for _ in range(3):
        window.add_page()
    done = window.undo_stack.index()
    assert done >= 3
    window._fill_undo_history()
    entries = [a for a in window.undo_history_menu.actions() if a.isEnabled()]
    assert len(entries) == done
    assert entries[0].text() == window.undo_stack.text(done - 1), "newest first"
    entries[1].trigger()                       # back to before the second newest
    assert window.undo_stack.index() == done - 2
    window.undo_stack.setIndex(0)
    window._fill_undo_history()
    assert [a.text() for a in window.undo_history_menu.actions()] == ["Nothing to undo"]


def test_open_recent_save_all_and_close_all(window, tmp_path, monkeypatch):
    from calcforge.ui import mainwindow
    first = tmp_path / "first.pdf"
    window.document.path = str(first)
    window.save_document()
    mainwindow.remember_recent_file(str(first))
    window.act_new_tab.trigger()
    second = tmp_path / "second.pdf"
    window.document.path = str(second)
    window.save_document()
    mainwindow.remember_recent_file(str(second))
    assert mainwindow.recent_files()[:2] == [str(second), str(first)]
    window._fill_recent()
    names = [a.text() for a in window.recent_menu.actions()]
    assert "second.pdf" in names[0] and "first.pdf" in names[1]
    # a change in each, then Save All
    for index in (0, 1):
        window.switch_to_document(index)
        window.add_page()
    window.switch_to_document(1)
    window.act_save_all.trigger()
    assert window._active_tab == 1
    for index in (0, 1):
        state = window._state_for_tab(index)
        assert not state["document"].modified and state["undo_stack"].isClean()
    window.act_close_all.trigger()
    assert len(window._open_documents) == 1 and not window.document.path
    # a file gone from the disk leaves the list
    first.unlink()
    monkeypatch.setattr(mainwindow.QMessageBox, "information", lambda *a, **k: None)
    window.open_recent(str(first))
    assert str(first) not in mainwindow.recent_files()
    window.open_recent(str(second))
    assert window.document.path == str(second)


def test_a_window_opened_while_dimmed_shows_dim_content_ticked(window, qapp):
    from calcforge.ui import scene as scene_module
    window.act_dim_content.trigger()
    assert scene_module.DIMMER["on"]
    other = window.open_new_window()                    # Window ▸ New Window
    qapp.processEvents()
    try:
        assert other.act_dim_content.isChecked(), "the page is dimmed, so its tick shows"
        other.act_dim_content.trigger()                 # one click undims everything
        assert not scene_module.DIMMER["on"]
        assert not window.act_dim_content.isChecked()
    finally:
        other.confirm_discard = lambda: True
        other.close()
        qapp.processEvents()
