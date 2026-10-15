"""The colour picker, as Bluebeam Revu's (the user's request, 2026-10-14):
one picker for every colour — Revu's 48 colours, No Color, the eyedropper,
custom colours and More Colors — with its own background in either theme."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

from calcforge.ui import colorpicker
from calcforge.ui.colorpicker import GRID, ColourPopup, _Dropper


def pump():
    for _ in range(3):
        QApplication.processEvents()


def test_revus_palette_no_color_and_the_eyedropper(qapp, monkeypatch):
    monkeypatch.setattr(colorpicker, "custom_colours", lambda: ["#123456"])
    popup = ColourPopup("#FF0000", allow_none=True)
    assert sum(len(row) for row in GRID) == 46          # + No Color + the eyedropper
    assert popup.buttons["#FF0000"].isChecked()
    assert popup.buttons[""].isEnabled()
    assert popup.dropper.toolTip().startswith("Eyedropper")
    assert popup.slots[0].isEnabled() and not popup.slots[1].isEnabled()
    got = []
    popup.picked.connect(got.append)
    popup.buttons["#0080FF"].click()
    assert got == ["#0080ff"] and popup.result == "#0080ff"
    # No Color only where a colour can be none
    assert not ColourPopup("#000000", allow_none=False).buttons[""].isEnabled()


def test_more_colors_opens_in_the_picker_and_is_kept(qapp, monkeypatch):
    kept = []
    monkeypatch.setattr(colorpicker, "remember", kept.append)
    popup = ColourPopup("#FF0000", allow_none=False)
    popup.show()
    popup.more.click()
    pump()
    editor = popup.editor
    assert editor is not None and not editor.isHidden()
    assert popup.more.arrowType() == Qt.UpArrow
    editor.hex.setText("#3366CC")
    editor.hex.editingFinished.emit()
    assert [b.value() for b in editor.rgb] == [0x33, 0x66, 0xCC]
    editor.add.click()
    assert popup.result == "#3366cc" and kept == ["#3366cc"]


def test_the_eyedropper_takes_the_colour_under_the_pointer(qapp):
    shot = QPixmap(40, 30)
    shot.fill(QColor("#ffffff"))
    from PySide6.QtGui import QPainter
    painter = QPainter(shot)
    painter.fillRect(QRect(10, 10, 5, 5), QColor("#c81e1e"))
    painter.end()
    dropper = _Dropper(shot, QRect(0, 0, 40, 30))
    assert dropper.colour_at(QPoint(12, 12)).name() == "#c81e1e"
    press = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(12, 12), QPointF(12, 12),
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    dropper.mousePressEvent(press)
    assert dropper.result == "#c81e1e"
    other = _Dropper(shot, QRect(0, 0, 40, 30))
    escape = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(12, 12), QPointF(12, 12),
                         Qt.RightButton, Qt.RightButton, Qt.NoModifier)
    other.mousePressEvent(escape)
    assert other.result is None, "a right-click leaves it"


def test_every_colour_button_uses_it(window):
    """The style bar's swatches, Color Processing, Format Cells, the rules
    and the markups list all open the same picker."""
    from calcforge.ui.widgets import ColorButton
    button = ColorButton("#ff0000", allow_none=True)
    seen = []
    button.colorChanged.connect(seen.append)
    colorpicker.ANSWERS[:] = ["#00ff00"]
    button.click()
    assert button.color() == "#00ff00" and seen == ["#00ff00"]
    colorpicker.ANSWERS[:] = [""]
    button.click()
    assert button.color() == "", "No Color"
    colorpicker.ANSWERS[:] = [None]
    button.click()
    assert button.color() == "", "left without a choice: unchanged"
    from calcforge.ui.colorprocess import _ColourButton
    changes = []
    swatch = _ColourButton("#000000", lambda: changes.append(1), allow_none=True)
    colorpicker.ANSWERS[:] = [""]
    swatch.click()
    assert swatch.colour is None and changes == [1]
    import inspect
    from calcforge.ui import calcmenu, celldialog, cfmanager, condformat, panels
    for module in (calcmenu, celldialog, cfmanager, condformat, panels):
        assert "QColorDialog.getColor" not in inspect.getsource(module), module.__name__


def test_the_eyedropper_works_over_a_modal_dialog_and_from_our_own_windows(window, monkeypatch):
    """Opened from Color Processing (a modal dialog), the held-still screen
    still takes the click — under the dialog it took none, and the
    application hung (the user, 2026-10-14). Where the system will not hand
    over the screen, it is the application's own windows that are shown."""
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QScreen
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout
    from calcforge.ui.colorpicker import pick_from_screen
    monkeypatch.setattr(QScreen, "grabWindow", lambda *a, **k: QPixmap())   # refused
    dialog = QDialog(window)
    dialog.setModal(True)
    patch = QLabel()
    patch.setFixedSize(60, 40)
    patch.setStyleSheet("background: #3a9b4f;")
    QVBoxLayout(dialog).addWidget(patch)
    dialog.show()
    QApplication.processEvents()
    seen = {}

    def click():
        dropper = next(w for w in QApplication.topLevelWidgets()
                       if isinstance(w, _Dropper) and w.isVisible())
        seen["modal"] = dropper.windowModality()
        where = dropper.mapFromGlobal(patch.mapToGlobal(QPoint(30, 20)))
        QApplication.sendEvent(dropper, QMouseEvent(
            QMouseEvent.MouseButtonPress, QPointF(where), QPointF(where),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    colorpicker.ANSWERS[:] = []
    QTimer.singleShot(50, click)
    QTimer.singleShot(3000, lambda: [w.close() for w in QApplication.topLevelWidgets()
                                     if isinstance(w, _Dropper)])      # never hang
    got = pick_from_screen()
    dialog.close()
    assert seen.get("modal") == Qt.ApplicationModal
    assert got == "#3a9b4f"


def test_a_colour_button_gone_while_its_picker_was_open_is_left_alone(window, monkeypatch):
    from calcforge.ui import widgets
    button = widgets.ColorButton("#ff0000")

    def chose(anchor, *_a, **_k):
        anchor.deleteLater()
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        return "#00ff00"
    monkeypatch.setattr(colorpicker, "choose", chose)
    button._pick()                       # no RuntimeError, no crash


def _filled(width, height, colour):
    shot = QPixmap(width, height)
    shot.fill(QColor(colour))
    return shot


def test_the_eyedropper_reaches_every_screen_and_a_scaled_one(qapp):
    """Revu's eyedropper takes a colour anywhere: the taskbar, another
    program, a second monitor (the user, 2026-10-15). One held-still picture
    per screen; the mouse is held by one, and a click over the other screen
    takes that screen's colour. A grab twice the size of its screen (a
    scaled display) is read at its own pixels."""
    from calcforge.ui.colorpicker import _Pick
    pick = _Pick()
    left = _Dropper(_filled(80, 60, "#204060"), QRect(0, 0, 40, 30), pick)   # 200 %
    right = _Dropper(_filled(40, 30, "#c03020"), QRect(40, 0, 40, 30), pick)
    pick.droppers[:] = [left, right]
    assert left.ratio == 2.0 and right.ratio == 1.0
    over_right = QMouseEvent(QMouseEvent.MouseMove, QPointF(50, 10), QPointF(50, 10),
                             Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    left.mouseMoveEvent(over_right)
    assert left.at is None and right.at == QPoint(10, 10), "the loupe follows to the other screen"
    click = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(50, 10), QPointF(50, 10),
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    left.mousePressEvent(click)
    assert pick.result == "#c03020"
    assert pick.ending and left.result == right.result == "#c03020"


def test_the_picker_swatches_are_drawn_at_the_screens_own_pixels(qapp):
    """Blurry next to Revu's (the user, 2026-10-15): a swatch made at 100 %
    and stretched to a 125 % or 150 % display. Asked for at a scale, it is
    drawn at that many pixels, its edge a single sharp pixel."""
    from PySide6.QtCore import QSize
    from calcforge.ui.colorpicker import swatch_icon
    for scale in (1.0, 1.25, 1.5, 2.0):
        pixmap = swatch_icon("#ff0000", 16).pixmap(QSize(16, 16), scale)
        assert pixmap.width() == round(16 * scale), scale
        image = pixmap.toImage()
        middle = image.pixelColor(pixmap.width() // 2, pixmap.height() // 2)
        assert middle.name() == "#ff0000"
        inside = image.pixelColor(1, pixmap.height() // 2)
        assert inside.name() == "#ff0000", f"the edge is one pixel at {scale}, not smeared"
