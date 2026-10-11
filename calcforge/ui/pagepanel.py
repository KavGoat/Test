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
        self._build_sheet(layout)
        layout.addStretch(1)

    # -- a spreadsheet page: Excel's Page Layout -------------------------------
    MARGINS = {"Normal": (0.7, 0.75, 0.7, 0.75), "Wide": (1.0, 1.0, 1.0, 1.0),
               "Narrow": (0.25, 0.75, 0.25, 0.75)}          # inches: left, top, right, bottom

    def _build_sheet(self, layout) -> None:
        """The spreadsheet's page layout and print settings, as in Excel's
        Page Layout tab — here as well as in its dialog (shown on a
        spreadsheet page only); each change applies at once, one undo step."""
        from PySide6.QtWidgets import QLineEdit
        box = self.sheet_box = QGroupBox("Spreadsheet")
        form = QFormLayout(box)
        self.margins = QComboBox()
        self.margins.addItems(list(self.MARGINS) + ["Custom"])
        self.margins.setToolTip("Excel's margins: Normal 0.7\"/0.75\", Wide 1\", Narrow 0.25\"/0.75\"")
        self.margins.activated.connect(lambda _i: self._margins_changed())
        form.addRow("Margins", self.margins)
        self.print_area = QLineEdit()
        self.print_area.setPlaceholderText("the columns that fit")
        self.print_area.editingFinished.connect(lambda: self._sheet_changed("print_area"))
        form.addRow("Print area", self.print_area)
        self.title_rows = QLineEdit()
        self.title_rows.setPlaceholderText("e.g. $1:$2")
        self.title_rows.editingFinished.connect(lambda: self._sheet_changed("titles"))
        form.addRow("Rows to repeat", self.title_rows)
        self.title_cols = QLineEdit()
        self.title_cols.setPlaceholderText("e.g. $A:$B")
        self.title_cols.editingFinished.connect(lambda: self._sheet_changed("title_cols"))
        form.addRow("Columns to repeat", self.title_cols)
        self.adjust = QSpinBox()
        self.adjust.setRange(10, 400)
        self.adjust.setSuffix(" %")
        self.adjust.setKeyboardTracking(False)
        self.adjust.valueChanged.connect(lambda _v: self._sheet_changed("scale"))
        form.addRow("Adjust to", self.adjust)
        # Excel's Fit to: N pages wide (unticked: as many across as it takes)
        self.fit_wide = QCheckBox("Fit to")
        self.fit_wide.toggled.connect(lambda _on: self._sheet_changed("fit_width"))
        self.fit_wide_n = QSpinBox()
        self.fit_wide_n.setRange(1, 99)
        self.fit_wide_n.setSuffix(" wide")
        self.fit_wide_n.setKeyboardTracking(False)
        self.fit_wide_n.valueChanged.connect(lambda _v: self._sheet_changed("fit_width"))
        wide = QHBoxLayout()
        wide.addWidget(self.fit_wide)
        wide.addWidget(self.fit_wide_n, 1)
        form.addRow("", wide)
        self.fit_tall = QSpinBox()
        self.fit_tall.setRange(0, 999)
        self.fit_tall.setSpecialValueText("automatic")
        self.fit_tall.setSuffix(" tall")
        self.fit_tall.setKeyboardTracking(False)
        self.fit_tall.valueChanged.connect(lambda _v: self._sheet_changed("fit_tall"))
        form.addRow("by", self.fit_tall)
        self.center_h = QCheckBox("Horizontally")
        self.center_v = QCheckBox("Vertically")
        centre = QHBoxLayout()
        centre.addWidget(self.center_h)
        centre.addWidget(self.center_v)
        self.center_h.toggled.connect(lambda _on: self._sheet_changed("center_h"))
        self.center_v.toggled.connect(lambda _on: self._sheet_changed("center_v"))
        form.addRow("Centre", centre)
        self.print_grid = QCheckBox("Gridlines")
        self.print_heads = QCheckBox("Headings")
        prints = QHBoxLayout()
        prints.addWidget(self.print_grid)
        prints.addWidget(self.print_heads)
        self.print_grid.toggled.connect(lambda _on: self._sheet_changed("print_gridlines"))
        self.print_heads.toggled.connect(lambda _on: self._sheet_changed("print_headings"))
        form.addRow("Print", prints)
        breaks = QHBoxLayout()
        insert = QPushButton("Insert break")
        insert.setToolTip("Page breaks above the selected cell's row and left of its column")
        insert.clicked.connect(self._insert_break)
        reset = QPushButton("Reset breaks")
        reset.setToolTip("Reset All Page Breaks")
        reset.clicked.connect(self._reset_breaks)
        breaks.addWidget(insert)
        breaks.addWidget(reset)
        form.addRow("Breaks", breaks)
        layout.addWidget(box)

    def _run(self):
        from .sheetlayout import _run_item
        window = self.window
        page = self.page()
        if page is None or page.sheet is None:
            return None
        item = _run_item(window, window.current_index)
        return item if item is not None and item.sheet is not None else None

    def _refresh_sheet(self, page) -> None:
        from ..sheet.pagination import options
        from ..sheet.refs import area_text, col_letters
        item = self._run()
        self.sheet_box.setVisible(item is not None)
        if item is None:
            return
        opts = options(item.sheet)
        setup = page.setup
        mm = (setup.margin_left, setup.margin_top, setup.margin_right, setup.margin_bottom)
        named = next((name for name, inches in self.MARGINS.items()
                      if all(abs(a - b * 25.4) < 0.05 for a, b in zip(mm, inches))), "Custom")
        self.margins.setCurrentText(named)
        area = opts["print_area"]
        self.print_area.setText(area_text(*area) if area else "")
        rows = opts["titles"]
        self.title_rows.setText(f"${rows[0] + 1}:${rows[1] + 1}" if rows else "")
        cols = opts.get("title_cols")
        self.title_cols.setText(f"${col_letters(cols[0])}:${col_letters(cols[1])}" if cols else "")
        self.adjust.setValue(int(opts.get("scale") or 100))
        self.fit_wide.setChecked(bool(opts["fit_width"]))
        self.fit_wide_n.setValue(max(1, int(opts["fit_width"] or 0)))
        self.fit_wide_n.setEnabled(bool(opts["fit_width"]))
        self.fit_tall.setValue(int(opts.get("fit_tall") or 0))
        self.adjust.setEnabled(not (opts["fit_width"] or opts.get("fit_tall")))
        self.center_h.setChecked(bool(opts["center_h"]))
        self.center_v.setChecked(bool(opts["center_v"]))
        self.print_grid.setChecked(bool(opts["print_gridlines"]))
        self.print_heads.setChecked(bool(opts["print_headings"]))

    def _sheet_changed(self, key: str) -> None:
        if self._filling:
            return
        from . import sheetlayout
        item = self._run()
        if item is None:
            return
        if key == "print_area":
            value = sheetlayout.parse_area(self.print_area.text())
        elif key == "titles":
            value = sheetlayout.parse_rows(self.title_rows.text())
        elif key == "title_cols":
            value = sheetlayout.parse_cols(self.title_cols.text())
        elif key == "scale":
            value = self.adjust.value()
        elif key == "fit_width":
            value = self.fit_wide_n.value() if self.fit_wide.isChecked() else False
        elif key == "fit_tall":
            value = self.fit_tall.value()
        else:
            value = {"center_h": self.center_h, "center_v": self.center_v,
                     "print_gridlines": self.print_grid,
                     "print_headings": self.print_heads}[key].isChecked()
        if value is False and key in ("print_area", "titles", "title_cols"):
            self.window.status_hint.setText("That is not a range (e.g. A1:K40, $1:$2, $A:$B)")
            self.refresh()
            return
        from ..sheet.pagination import options
        if options(item.sheet).get(key) == value:
            return
        sheetlayout.change_options(self.window, item, "Page layout", **{key: value})
        self.refresh()

    def _margins_changed(self) -> None:
        if self._filling:
            return
        inches = self.MARGINS.get(self.margins.currentText())
        if inches is None:
            return
        setup = PageSetup.from_dict(self.page().setup.to_dict())
        (setup.margin_left, setup.margin_top, setup.margin_right,
         setup.margin_bottom) = (v * 25.4 for v in inches)
        self.window.set_page_setup(setup)
        self.refresh()

    def _insert_break(self) -> None:
        from . import sheetlayout
        item = self._run()
        tables = self.window.view.tables
        if item is None:
            return
        row, col = tables.active if tables.item is item else (0, 0)
        if row <= 0 and col <= 0:
            self.window.status_hint.setText("Pick a cell below row 1 or right of column A for the break")
            return
        sheetlayout.insert_break(self.window, item, row, col)

    def _reset_breaks(self) -> None:
        from . import sheetlayout
        item = self._run()
        if item is not None:
            sheetlayout.reset_breaks(self.window, item)

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
            self._refresh_sheet(page)
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
