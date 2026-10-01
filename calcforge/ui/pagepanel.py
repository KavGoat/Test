"""The Page panel: the current page's paper, scale and viewports in one place.

It follows the page being looked at. Everything in it applies as soon as it
is changed: paper size and orientation, the scale across and (when it
differs) down the page, the units and decimal places measurements are shown
in, and the viewports — regions of the sheet at a scale of their own.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QListWidget, QSizePolicy,
                               QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
                               QWidget)

from ..core.document import LANDSCAPE, PAGE_SIZES, PORTRAIT, PageScale, PageSetup
from .dialogs import ScaleDialog, ratio_text, read_ratio
from .widgets import UnitCombo


class PagePanel(QScrollArea):
    """Paper, scale and viewports of the page in view."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self._filling = False
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        self.setWidget(body)

        # -- paper ---------------------------------------------------------
        paper = QGroupBox("Page")
        form = QFormLayout(paper)
        self.size = QComboBox()
        self.size.setObjectName("pageSize")
        self.size.addItems(list(PAGE_SIZES) + ["Custom"])
        self.size.activated.connect(lambda _i: self._paper_changed(self.size))
        form.addRow("Paper", self.size)
        self.orientation = QComboBox()
        self.orientation.setObjectName("pageOrientation")
        self.orientation.addItems(["Portrait", "Landscape"])
        self.orientation.activated.connect(lambda _i: self._paper_changed(self.orientation))
        form.addRow("Orientation", self.orientation)
        sizes = QHBoxLayout()
        self.width_mm = QDoubleSpinBox()
        self.height_mm = QDoubleSpinBox()
        for box in (self.width_mm, self.height_mm):
            box.setRange(20, 5000)
            box.setDecimals(1)
            box.setSuffix(" mm")
            box.setKeyboardTracking(False)
            box.valueChanged.connect(lambda _v, b=box: self._paper_changed(b))
        # the two boxes share the width, with the × tight between them
        by = QLabel("×")
        by.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        for box in (self.width_mm, self.height_mm):
            box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sizes.addWidget(self.width_mm, 1)
        sizes.addWidget(by)
        sizes.addWidget(self.height_mm, 1)
        form.addRow("Size", sizes)
        self.all_pages = QCheckBox("Apply to all pages")
        self.all_pages.setToolTip("Paper changes go to every page, not just this one")
        form.addRow("", self.all_pages)
        layout.addWidget(paper)

        # -- scale ---------------------------------------------------------
        scale = QGroupBox("Scale")
        form = QFormLayout(scale)
        self.ratio = self._ratio_box("pageScaleX")
        form.addRow("Scale", self.ratio)
        self.separate_y = QCheckBox("Separate Y scale")
        self.separate_y.setToolTip("Use a different scale down the page than across it")
        self.separate_y.toggled.connect(self._scale_changed)
        form.addRow("", self.separate_y)
        self.y_ratio = self._ratio_box("pageScaleY")
        form.addRow("Y scale", self.y_ratio)
        self.calibrated_note = QLabel()
        self.calibrated_note.setWordWrap(True)
        form.addRow("", self.calibrated_note)
        calibrate = QPushButton("Calibrate…")
        calibrate.setToolTip("Click each end of something you know the length "
                             "of, then type that length")
        calibrate.clicked.connect(lambda: self.window.start_calibrating())
        form.addRow("", calibrate)
        self.length_unit = UnitCombo("m")
        self.length_unit.setObjectName("pageLengthUnit")
        self.length_unit.setToolTip("Units lengths are shown in")
        self.length_unit.activated.connect(lambda _i: self._scale_changed())
        self.length_unit.lineEdit().editingFinished.connect(self._scale_changed)
        form.addRow("Length unit", self.length_unit)
        self.area_unit = UnitCombo("m^2")
        self.area_unit.setObjectName("pageAreaUnit")
        self.area_unit.setToolTip("Units areas are shown in")
        self.area_unit.activated.connect(lambda _i: self._scale_changed())
        self.area_unit.lineEdit().editingFinished.connect(self._scale_changed)
        form.addRow("Area unit", self.area_unit)
        self.precision = QSpinBox()
        self.precision.setObjectName("pagePrecision")
        self.precision.setRange(0, 6)
        self.precision.setToolTip("Decimal places measurements are shown to")
        self.precision.valueChanged.connect(lambda _v: self._scale_changed())
        form.addRow("Decimal places", self.precision)
        layout.addWidget(scale)

        # -- viewports -----------------------------------------------------
        ports = QGroupBox("Viewports")
        column = QVBoxLayout(ports)
        self.viewports = QListWidget()
        self.viewports.setObjectName("pageViewports")
        self.viewports.setToolTip("Regions of this page at their own scale; "
                                  "double-click one to change it")
        self.viewports.currentRowChanged.connect(self._viewport_picked)
        self.viewports.itemDoubleClicked.connect(lambda _item: self.edit_viewport())
        self.viewports.setMinimumHeight(70)
        column.addWidget(self.viewports)
        row = QHBoxLayout()
        add = QPushButton("Add")
        add.setToolTip("Drag a region of the sheet drawn at its own scale")
        add.clicked.connect(lambda: self.window.select_tool("viewport"))
        self.edit_button = QPushButton("Edit…")
        self.edit_button.setToolTip("Rename it or change its scale")
        self.edit_button.clicked.connect(self.edit_viewport)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_viewport)
        for button in (add, self.edit_button, self.delete_button):
            row.addWidget(button)
        column.addLayout(row)
        layout.addWidget(ports)
        layout.addStretch(1)

    def _ratio_box(self, name: str) -> QComboBox:
        box = QComboBox()
        box.setObjectName(name)
        box.setEditable(True)
        box.addItems(ScaleDialog.RATIOS)
        box.setToolTip("A ratio such as 1:100")
        box.activated.connect(lambda _i: self._scale_changed())
        box.lineEdit().editingFinished.connect(self._scale_changed)
        return box

    # -- reading the page ---------------------------------------------------
    def page(self):
        return self.window.current_page()

    def refresh(self) -> None:
        """Show the page in view."""
        page = self.page()
        if page is None:
            return
        self._filling = True
        try:
            setup = page.setup
            self.size.setCurrentText(setup.size_name if setup.size_name in PAGE_SIZES
                                     else "Custom")
            self.orientation.setCurrentIndex(1 if setup.orientation == LANDSCAPE else 0)
            self.width_mm.setValue(setup.width_mm)
            self.height_mm.setValue(setup.height_mm)
            scale = page.scale
            calibrated = scale.is_calibrated()
            self.ratio.setCurrentText(ratio_text(scale.ratio()) if calibrated else "1:1")
            self.separate_y.setChecked(calibrated and scale.separate_y())
            self.y_ratio.setCurrentText(ratio_text(scale.y_ratio()) if calibrated
                                        else "1:1")
            self.y_ratio.setEnabled(self.separate_y.isChecked())
            ratio = scale.label.startswith("1:") or scale.label.startswith("X ")
            self.calibrated_note.setText("" if not calibrated or ratio
                                         else f"Calibrated: {scale.label}")
            self.calibrated_note.setVisible(bool(self.calibrated_note.text()))
            self.length_unit.setCurrentText(scale.display_unit)
            self.area_unit.setCurrentText(scale.area_unit)
            self.precision.setValue(scale.precision)
            row = self.viewports.currentRow()
            self.viewports.clear()
            for viewport in page.viewports:
                self.viewports.addItem(f"{viewport.name}  —  {viewport.scale.label}")
            if self.viewports.count():
                self.viewports.setCurrentRow(min(max(row, 0), self.viewports.count() - 1))
            has = bool(page.viewports)
            self.edit_button.setEnabled(has)
            self.delete_button.setEnabled(has)
        finally:
            self._filling = False

    # -- changing it --------------------------------------------------------
    def _paper_changed(self, source) -> None:
        if self._filling:
            return
        page = self.page()
        setup = PageSetup.from_dict(page.setup.to_dict())
        if source is self.size and self.size.currentText() in PAGE_SIZES:
            setup.apply_size(self.size.currentText())
        elif source in (self.width_mm, self.height_mm):
            setup.size_name = "Custom"
            setup.width_mm = self.width_mm.value()
            setup.height_mm = self.height_mm.value()
        setup.orientation = LANDSCAPE if self.orientation.currentIndex() == 1 else PORTRAIT
        self.window.set_page_setup(setup, self.all_pages.isChecked())
        self.refresh()

    def _scale_changed(self, *_args) -> None:
        if self._filling:
            return
        self.y_ratio.setEnabled(self.separate_y.isChecked())
        page = self.page()
        old = page.scale
        ratio = read_ratio(self.ratio.currentText())
        y_ratio = read_ratio(self.y_ratio.currentText()) if self.separate_y.isChecked() \
            else ratio
        if ratio is None or y_ratio is None:
            self.refresh()
            return
        unchanged_ratio = (old.is_calibrated() and old.ratio() is not None
                           and ratio_text(old.ratio()) == ratio_text(ratio)
                           and abs((old.y_ratio() or 0) - y_ratio) < 1e-9 * y_ratio)
        if unchanged_ratio:
            scale = PageScale.from_dict(old.to_dict())
        elif not old.is_calibrated() and ratio == 1 and y_ratio == 1:
            scale = PageScale.from_dict(old.to_dict())
        else:
            scale = PageScale.from_ratio(ratio, y_ratio=y_ratio)
        scale.display_unit = self.length_unit.currentText() or "m"
        scale.area_unit = self.area_unit.currentText() or "m^2"
        scale.precision = self.precision.value()
        if scale.to_dict() != old.to_dict():
            self.window.set_page_scale(scale)
        self.refresh()

    # -- viewports ------------------------------------------------------------
    def _chosen(self):
        page = self.page()
        row = self.viewports.currentRow()
        if 0 <= row < len(page.viewports):
            return page.viewports[row]
        return None

    def _viewport_picked(self, _row: int) -> None:
        """Picking a viewport in the list shows its frame on the page."""
        if self._filling:
            return
        page = self.page()
        if page.frame is not None:
            page.frame.set_active_viewport(self._chosen())

    def edit_viewport(self) -> None:
        viewport = self._chosen()
        if viewport is not None:
            self.window.edit_viewport(self.page(), viewport)
            self.refresh()

    def delete_viewport(self) -> None:
        viewport = self._chosen()
        if viewport is not None:
            self.window.delete_viewport(self.page(), viewport)
            self.refresh()
