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
