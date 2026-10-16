"""Revu's Change Multiple Colors (the user's choice, 2026-10-15): with several
markups selected, one colour they use — line, fill, text or hatch — becomes
another, in all of them at once.

Opened from a markup's right-click menu (Change Colors…) or the Properties
panel's Appearance section when more than one markup is selected. The Source
Color list holds only the colours the selection uses; Before and After show
the selection either way.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QGridLayout,
                               QLabel, QToolButton, QVBoxLayout)

#: The style's colours a markup can carry.
FIELDS = ("stroke", "fill", "text_color", "hatch_color")


def colours_in(items) -> list:
    """Every colour the markups use, in the order first met."""
    seen: list = []
    for item in items:
        style = getattr(item, "style", None)
        if style is None:
            continue
        for field in FIELDS:
            value = (getattr(style, field, "") or "").lower()
            if field == "hatch_color" and not getattr(style, "hatch", ""):
                continue                  # a hatch colour with no hatch shows nowhere
            if field == "text_color" and type(item).__module__.endswith("items.shapes"):
                continue                  # a shape has no words to colour
            if value and value not in seen:
                seen.append(value)
    return seen


def recolour(items, source: str, destination: str) -> int:
    """*source* becomes *destination* wherever the markups use it. How many
    colours were changed."""
    source, changed = (source or "").lower(), 0
    for item in items:
        style = getattr(item, "style", None)
        if style is None:
            continue
        for field in FIELDS:
            if (getattr(style, field, "") or "").lower() == source and source:
                setattr(style, field, destination)
                changed += 1
    return changed


def _picture(items, size: QSize) -> QPixmap:
    """The markups as they look, scaled into *size*."""
    picture = QPixmap(size)
    picture.fill(QColor("#ffffff"))
    if not items:
        return picture
    scene = items[0].scene()
    if scene is None:
        return picture
    bounds = QRectF()
    for item in items:
        rect = item.sceneBoundingRect()
        bounds = rect if bounds.isNull() else bounds.united(rect)
    bounds = bounds.adjusted(-4, -4, 4, 4)
    hidden = [other for other in scene.items()
              if other.isVisible() and other.parentItem() is not None
              and other not in items and not any(other is i or i.isAncestorOf(other)
                                                 for i in items)
              and hasattr(other, "style")]
    selected = [item for item in items if item.isSelected()]
    for other in hidden:
        other.setVisible(False)
    for item in selected:
        item.setSelected(False)           # no handles in the picture
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.Antialiasing, True)
    scene.render(painter, QRectF(picture.rect()).adjusted(2, 2, -2, -2), bounds,
                 Qt.KeepAspectRatio)
    painter.end()
    for other in hidden:
        other.setVisible(True)
    for item in selected:
        item.setSelected(True)
    return picture


class ChangeColorsDialog(QDialog):
    def __init__(self, window, items):
        super().__init__(window)
        self.window = window
        self.items = list(items)
        self.setWindowTitle("Change Multiple Colours")
        self.setObjectName("changeMultipleColors")
        self.source: Optional[str] = None
        self.destination: Optional[str] = None
        outer = QVBoxLayout(self)
        group = QGroupBox("Colours")
        grid = QGridLayout(group)
        form = QFormLayout()
        self.source_button = self._swatch_button("Source Colour: a colour the selection uses")
        self.source_button.clicked.connect(self._pick_source)
        self.destination_button = self._swatch_button("Destination Colour: what it becomes")
        self.destination_button.clicked.connect(self._pick_destination)
        form.addRow("Source Colour:", self.source_button)
        form.addRow("Destination Colour:", self.destination_button)
        grid.addLayout(form, 0, 0, 1, 2)
        grid.addWidget(QLabel("Before"), 1, 0)
        grid.addWidget(QLabel("After"), 1, 1)
        self.before = QLabel()
        self.after = QLabel()
        for preview in (self.before, self.after):
            preview.setFixedSize(150, 130)
            preview.setStyleSheet("border: 1px solid #808080; background: #ffffff;")
        grid.addWidget(self.before, 2, 0)
        grid.addWidget(self.after, 2, 1)
        outer.addWidget(group)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok = buttons.button(QDialogButtonBox.Ok)
        outer.addWidget(buttons)
        self.found = colours_in(self.items)
        if self.found:
            self.set_source(self.found[0])
        self._refresh()

    @staticmethod
    def _swatch_button(tip: str) -> QToolButton:
        button = QToolButton()
        button.setFixedSize(26, 22)
        button.setIconSize(QSize(18, 16))
        button.setToolTip(tip)
        return button

    def _show(self, button: QToolButton, colour: Optional[str]) -> None:
        from .colorpicker import swatch_icon
        button.setIcon(swatch_icon(colour or "", 16))

    def set_source(self, colour: Optional[str]) -> None:
        self.source = colour.lower() if colour else None
        self._refresh()

    def set_destination(self, colour: Optional[str]) -> None:
        self.destination = colour.lower() if colour else None
        self._refresh()

    def _pick_source(self) -> None:
        from .colorpicker import choose_found
        got = choose_found(self.source_button, self.found, self.source)
        if got:
            self.set_source(got)

    def _pick_destination(self) -> None:
        from .colorpicker import choose
        got = choose(self.destination_button, self.destination or self.source)
        if got:
            self.set_destination(got)

    def _refresh(self) -> None:
        self._show(self.source_button, self.source)
        self._show(self.destination_button, self.destination)
        self.ok.setEnabled(bool(self.source and self.destination
                                and self.source != self.destination))
        self.before.setPixmap(_picture(self.items, self.before.size()))
        if self.source and self.destination:
            kept = [{field: getattr(i.style, field, "") for field in FIELDS}
                    for i in self.items]
            recolour(self.items, self.source, self.destination)
            self._restyle()
            self.after.setPixmap(_picture(self.items, self.after.size()))
            for item, values in zip(self.items, kept):
                for field, value in values.items():
                    setattr(item.style, field, value)
            self._restyle()
        else:
            self.after.setPixmap(_picture(self.items, self.after.size()))

    def _restyle(self) -> None:
        for item in self.items:
            if hasattr(item, "apply_style"):
                item.apply_style()
            item.update()

    def apply(self) -> int:
        """Make the change, as one step of the undo history."""
        if not (self.source and self.destination):
            return 0
        view = self.window.view
        view.begin_snapshot()
        changed = recolour(self.items, self.source, self.destination)
        for item in self.items:
            item.touch()
            item.prepareGeometryChange()
        self._restyle()
        view.commit_snapshot("Change Colours")
        return changed


def change_multiple_colors(window, items) -> int:
    """Open the dialog for *items*; how many colours were changed."""
    dialog = ChangeColorsDialog(window, items)
    if dialog.exec() != QDialog.Accepted:
        return 0
    changed = dialog.apply()
    if hasattr(window, "refresh_selection"):
        window.refresh_selection()
    return changed
