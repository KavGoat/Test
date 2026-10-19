"""A Checkbox's own settings, in the Properties panel and on the Properties
toolbar (items/checkbox.py).

The panel's Checkbox section manages the options: each one a row to tick and
to rename in place, with Add Option, Remove Option, Move Up and Move Down;
then the Box shape, the Mark a ticked box shows, Multiple Selection, the box
and mark colours and the spacing between options. Every change is one undo
step (PropertiesPanel._apply). The toolbar carries Box ▾, Mark ▾ and
Multiple, the settings that fit on it.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox,
                               QListWidget, QListWidgetItem, QToolButton)

from ..items.checkbox import MARKS, SHAPES, CheckboxItem

#: The Properties toolbar's group of a Checkbox's controls (propbar.CHECKBOX).
GROUP = "checkbox"


def picture(shape: str, mark: str = "", size: int = 20) -> QIcon:
    """A box of *shape*, showing *mark* when one is given: for the lists, in
    the theme's ink."""
    from PySide6.QtGui import QPen
    from ..items.checkbox import box_path, draw_mark
    from . import icons
    ratio = 2
    pixmap = QPixmap(size * ratio, size * ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(ratio, ratio)
    side = size * 0.55
    box = QRectF((size - side) / 2, (size - side) / 2 + 1, side, side)
    pen = QPen(QColor(icons.INK))
    pen.setWidthF(1.3)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(box_path(shape, box))
    if mark:
        draw_mark(painter, mark, shape, box, QColor(icons.INK))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return QIcon(pixmap)


def refresh_bar_icons(window) -> None:
    """The toolbar's Box ▾ and Mark ▾ pictures, in the theme's ink."""
    if not hasattr(window, "checkbox_shape_combo"):
        return
    for index, (key, _name) in enumerate(SHAPES):
        window.checkbox_shape_combo.setItemIcon(index, picture(key))
    for index, (key, _name) in enumerate(MARKS):
        window.checkbox_mark_combo.setItemIcon(index, picture("square", key))


def _checkboxes(items) -> list:
    return [item for item in items if isinstance(item, CheckboxItem)]


# ---------------------------------------------------------------------------
# the Properties panel
# ---------------------------------------------------------------------------

def add_section(panel, item: CheckboxItem, look_only: bool = False) -> None:
    """The Checkbox section of the Properties panel, for *item*. *look_only*
    (a markup style being edited): its look, not its options."""
    from .panels import _row, _spin
    from .widgets import ColorButton

    form = panel._group("Checkbox")
    if not look_only:
        options = QListWidget()
        options.setObjectName("checkboxOptions")
        options.setToolTip("The options: tick one to tick it on the page; "
                           "double-click or F2 to rename it")
        options.setEditTriggers(QAbstractItemView.DoubleClicked
                                | QAbstractItemView.EditKeyPressed
                                | QAbstractItemView.SelectedClicked)
        words, ticks = item.options(), item.ticks()
        for text, on in zip(words, ticks):
            row = QListWidgetItem(text)
            row.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable
                         | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
            row.setCheckState(Qt.Checked if on else Qt.Unchecked)
            options.addItem(row)
        # every option seen (up to eight, then it scrolls), cut short with
        # "…" rather than scrolled sideways
        options.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        options.setTextElideMode(Qt.ElideRight)
        rows = max(min(len(words), 8), 2)
        height = options.sizeHintForRow(0) if options.count() else 20
        options.setFixedHeight(height * rows + 2 * options.frameWidth() + 6)
        picked = getattr(panel, "_checkbox_row", 0)
        if options.count():
            options.setCurrentRow(max(0, min(picked, options.count() - 1)))
        options.itemChanged.connect(lambda row: _row_changed(panel, options, row))
        options.currentRowChanged.connect(
            lambda number: setattr(panel, "_checkbox_row", number))
        form.addRow("Options:", options)

        def button(text: str, tip: str, name: str, run) -> QToolButton:
            made = QToolButton()
            made.setText(text)
            made.setToolTip(tip)
            made.setObjectName(name)
            made.clicked.connect(lambda _checked=False: run())
            return made
        add = button("Add Option", "Add an option after the one picked",
                     "checkboxAddOption", lambda: add_option(panel, options))
        remove = button("Remove Option", "Take the picked option away",
                        "checkboxRemoveOption", lambda: remove_option(panel, options))
        up = button("Move Up", "Move the picked option up", "checkboxMoveUp",
                    lambda: move_option(panel, options, -1))
        down = button("Move Down", "Move the picked option down", "checkboxMoveDown",
                      lambda: move_option(panel, options, 1))
        form.addRow("", _row(add, remove))
        form.addRow("", _row(up, down))

    shape = QComboBox()
    shape.setObjectName("checkboxShape")
    shape.setToolTip("The boxes' shape")
    for key, name in SHAPES:
        shape.addItem(picture(key), name, key)
    shape.setCurrentIndex(max(shape.findData(item.box_shape), 0))
    shape.currentIndexChanged.connect(lambda _i: panel._apply(
        lambda i: _set(i, "box_shape", shape.currentData()), "Checkbox shape"))
    form.addRow("Box:", shape)

    mark = QComboBox()
    mark.setObjectName("checkboxMark")
    mark.setToolTip("What a ticked box shows")
    for key, name in MARKS:
        mark.addItem(picture(item.box_shape, key), name, key)
    mark.setCurrentIndex(max(mark.findData(item.mark), 0))
    mark.currentIndexChanged.connect(lambda _i: panel._apply(
        lambda i: _set(i, "mark", mark.currentData()), "Checkbox mark"))
    form.addRow("Mark:", mark)

    several = QCheckBox("Multiple Selection")
    several.setObjectName("checkboxMultiple")
    several.setToolTip("Several options may be ticked; off, ticking one unticks "
                       "the others")
    several.setChecked(bool(item.multiple))
    several.toggled.connect(lambda on: panel._apply(
        lambda i: i.set_multiple(on) if isinstance(i, CheckboxItem) else None,
        "Multiple selection"))
    form.addRow("", several)

    text = item.style.text_color
    box_colour = ColorButton(item.box_color or text, label="Box colour")
    box_colour.setObjectName("checkboxBoxColour")
    box_colour.colorChanged.connect(lambda value: panel._apply(
        lambda i: _set(i, "box_color", value), "Box colour"))
    mark_colour = ColorButton(item.mark_color or text, label="Mark colour")
    mark_colour.setObjectName("checkboxMarkColour")
    mark_colour.colorChanged.connect(lambda value: panel._apply(
        lambda i: _set(i, "mark_color", value), "Mark colour"))
    form.addRow("Box Colour:", _row(box_colour))
    form.addRow("Mark Colour:", _row(mark_colour))

    spacing = _spin(item.option_gap, 0.0, 5.0, 2, 0.05)
    spacing.setObjectName("checkboxOptionSpacing")
    spacing.setSuffix(" × size")
    spacing.setToolTip("The space between one option and the next, as a share of "
                       "the font size, on top of the line spacing")
    spacing.valueChanged.connect(lambda value: panel._slide(
        lambda i: _set(i, "option_gap", float(value)), "Option spacing"))
    form.addRow("Option Spacing:", spacing)

    from PySide6.QtWidgets import QWidget

    if panel.body.findChild(QDoubleSpinBox, "lineSpacing") is None and \
            panel.body.findChild(QWidget, "lineSpacingPanel") is None:
        # (the text box's own Line Spacing, where the panel has none yet)
        lines = _spin(float(getattr(item.style, "line_spacing", 1.0) or 1.0),
                      0.5, 5.0, 2, 0.1)
        lines.setObjectName("lineSpacing")
        lines.setToolTip("How far apart the lines are, as a multiple of single spacing")
        lines.valueChanged.connect(lambda value: panel._slide(
            lambda i: setattr(i.style, "line_spacing", float(value)), "Line spacing"))
        form.addRow("Line Spacing:", lines)


def _set(item, name: str, value) -> None:
    if isinstance(item, CheckboxItem):
        setattr(item, name, value)


def _again(panel) -> None:
    """Show the panel afresh once the change is in (the list's rows moved)."""
    QTimer.singleShot(0, lambda: panel.show_items(list(panel._items))
                      if panel._items else None)


def _row_changed(panel, options, row) -> None:
    if panel._building:
        return
    number = options.row(row)
    item = next(iter(_checkboxes(panel._items)), None)
    if item is None or not 0 <= number < len(item.options()):
        return
    on = row.checkState() == Qt.Checked
    words = row.text()
    panel._checkbox_row = number
    if on != item.is_checked(number):
        panel._apply(lambda i: i.set_checked(number, on),
                     ("Tick " if on else "Untick ") + (words.strip() or "option"))
        if not item.multiple:
            _again(panel)                 # the others it unticked
    elif words != item.options()[number]:
        panel._apply(lambda i: i.rename_option(number, words), "Rename option")


def _picked(options) -> int:
    number = options.currentRow()
    return number if number >= 0 else options.count() - 1


def add_option(panel, options) -> None:
    item = next(iter(_checkboxes(panel._items)), None)
    if item is None:
        return
    at = _picked(options) + 1
    words = f"Option {len(item.options()) + 1}"
    panel._apply(lambda i: i.add_option(words, at), "Add option")
    panel._checkbox_row = at
    _again(panel)


def remove_option(panel, options) -> None:
    number = _picked(options)
    if number < 0:
        return
    panel._apply(lambda i: i.remove_option(number), "Remove option")
    panel._checkbox_row = max(number - 1, 0)
    _again(panel)


def move_option(panel, options, step: int) -> None:
    number = _picked(options)
    if number < 0 or not 0 <= number + step < options.count():
        return
    panel._apply(lambda i: i.move_option(number, step),
                 "Move option up" if step < 0 else "Move option down")
    panel._checkbox_row = number + step
    _again(panel)


# ---------------------------------------------------------------------------
# the Properties toolbar
# ---------------------------------------------------------------------------

def build_bar(window, put, label) -> None:
    """Box ▾, Mark ▾ and Multiple on the Properties toolbar."""
    from .propbar import IconCombo
    from .widgets import checked_list

    w = window
    put(GROUP, label("Box:"))
    w.checkbox_shape_combo = IconCombo(52)
    w.checkbox_shape_combo.setObjectName("checkboxShapeBar")
    w.checkbox_shape_combo.setProperty("what", "Box: ")
    w.checkbox_shape_combo.setIconSize(QSize(20, 20))
    for key, name in SHAPES:
        w.checkbox_shape_combo.addItem(picture(key), name, key)
    checked_list(w.checkbox_shape_combo)
    w.checkbox_shape_combo.currentIndexChanged.connect(
        lambda _i: change(w, "box_shape", w.checkbox_shape_combo.currentData(),
                          "Checkbox shape"))
    put(GROUP, w.checkbox_shape_combo)
    put(GROUP, label("Mark:"))
    w.checkbox_mark_combo = IconCombo(52)
    w.checkbox_mark_combo.setObjectName("checkboxMarkBar")
    w.checkbox_mark_combo.setProperty("what", "Mark: ")
    w.checkbox_mark_combo.setIconSize(QSize(20, 20))
    for key, name in MARKS:
        w.checkbox_mark_combo.addItem(picture("square", key), name, key)
    checked_list(w.checkbox_mark_combo)
    w.checkbox_mark_combo.currentIndexChanged.connect(
        lambda _i: change(w, "mark", w.checkbox_mark_combo.currentData(), "Checkbox mark"))
    put(GROUP, w.checkbox_mark_combo)
    w.checkbox_multiple_button = QToolButton()
    w.checkbox_multiple_button.setObjectName("checkboxMultipleBar")
    w.checkbox_multiple_button.setCheckable(True)
    w.checkbox_multiple_button.setText("Multiple")
    w.checkbox_multiple_button.setToolTip(
        "Multiple selection: several options may be ticked; off, ticking one "
        "unticks the others")
    w.checkbox_multiple_button.toggled.connect(
        lambda on: change(w, "multiple", bool(on), "Multiple selection"))
    put(GROUP, w.checkbox_multiple_button)


def sync_bar(window, active) -> None:
    """The toolbar's Checkbox controls showing *active*'s settings."""
    if not hasattr(window, "checkbox_shape_combo") or not isinstance(active, CheckboxItem):
        return
    for control, value, method in (
            (window.checkbox_shape_combo,
             max(window.checkbox_shape_combo.findData(active.box_shape), 0),
             "setCurrentIndex"),
            (window.checkbox_mark_combo,
             max(window.checkbox_mark_combo.findData(active.mark), 0), "setCurrentIndex"),
            (window.checkbox_multiple_button, bool(active.multiple), "setChecked")):
        control.blockSignals(True)
        getattr(control, method)(value)
        control.blockSignals(False)


def _put_on(item, name: str, value) -> None:
    if name == "multiple":
        item.set_multiple(value)
    else:
        setattr(item, name, value)
    item.update()


def change(window, name: str, value, description: str) -> None:
    """A toolbar control moved: the selected Checkboxes as one undo step, a
    markup style being edited, or the next Checkbox's look."""
    from . import toolsets
    if window._edit_markup_style(lambda item: _put_on(item, name, value)
                                 if isinstance(item, CheckboxItem) else None):
        return
    items = _checkboxes(window.selected_items())
    if not items:
        item = window._style_default_item()
        if isinstance(item, CheckboxItem):
            window.apply_default_style(item)
            _put_on(item, name, value)
            toolsets.remember_default(item)
        return
    if all(getattr(item, name) == value for item in items):
        return
    window.view.begin_snapshot(window.view.involved_frames(*items))
    for item in items:
        _put_on(item, name, value)
        item.touch()
    window.view.commit_snapshot(description)
    window.properties_panel.show_items(window.panel_subjects())
