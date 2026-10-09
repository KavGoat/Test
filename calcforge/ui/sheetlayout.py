"""A spreadsheet's page layout: Excel's Page Layout options for a run of
spreadsheet pages (items/sheetpage.py, sheet/pagination.py).

Fit to page width, Print Area, Print Titles, centring, printed gridlines and
headings, and the manual page breaks (Insert / Remove Page Break, Reset All
Page Breaks). Each change is one undo step.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QLineEdit, QVBoxLayout)

from ..sheet.pagination import options
from ..sheet.refs import CellRef, area_text, parse_range


def _run_item(window, index: int):
    from ..items.sheetpage import run_item_for
    page = window.document.pages[index]
    return run_item_for(page.frame) if page.frame is not None else None


def change_options(window, item, label: str, **changes) -> None:
    """Change the sheet's page options as one undo step."""
    sheet = item.sheet
    if sheet is None:
        return
    view = window.view
    view.begin_snapshot(item.run_frames())
    sheet.workbook.set_page_options(sheet, **changes)
    item.relayout()
    view.commit_snapshot(label)


def parse_area(text: str) -> Optional[list]:
    """"A1:K40" → [top, left, bottom, right]; "" → None; nonsense → False."""
    text = (text or "").strip()
    if not text:
        return None
    ref = parse_range(text.replace("$", ""))
    if ref is None:
        return False
    if isinstance(ref, CellRef):
        return [ref.row, ref.col, ref.row, ref.col]
    a, b = ref.first, ref.last
    return [min(a.row, b.row), min(a.col, b.col), max(a.row, b.row), max(a.col, b.col)]


def parse_rows(text: str) -> Optional[list]:
    """"1:2" or "$1:$2" or "3" → [first, last] rows; "" → None; nonsense → False."""
    text = (text or "").strip().replace("$", "")
    if not text:
        return None
    a, _, b = text.partition(":")
    b = b or a
    if not (a.isdigit() and b.isdigit()) or int(a) < 1 or int(b) < 1:
        return False
    first, last = sorted((int(a) - 1, int(b) - 1))
    return [first, last]


class SheetLayoutDialog(QDialog):
    def __init__(self, sheet, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Page layout — {sheet.name}")
        opts = options(sheet)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.area = QLineEdit(area_text(*opts["print_area"]) if opts["print_area"] else "")
        self.area.setPlaceholderText("the columns that fit on the page")
        form.addRow("Print area:", self.area)
        titles = opts["titles"]
        self.titles = QLineEdit(f"${titles[0] + 1}:${titles[1] + 1}" if titles else "")
        self.titles.setPlaceholderText("e.g. 1:2")
        form.addRow("Rows to repeat at top:", self.titles)
        layout.addLayout(form)
        self.fit = QCheckBox("Fit all columns to the page width")
        self.fit.setChecked(bool(opts["fit_width"]))
        self.center_h = QCheckBox("Centre on page horizontally")
        self.center_h.setChecked(bool(opts["center_h"]))
        self.center_v = QCheckBox("Centre on page vertically")
        self.center_v.setChecked(bool(opts["center_v"]))
        self.gridlines = QCheckBox("Print gridlines")
        self.gridlines.setChecked(bool(opts["print_gridlines"]))
        self.headings = QCheckBox("Print row and column headings")
        self.headings.setChecked(bool(opts["print_headings"]))
        self.screen_grid = QCheckBox("Show gridlines on screen")
        self.screen_grid.setChecked(bool(sheet.show_gridlines))
        for box in (self.fit, self.center_h, self.center_v, self.gridlines, self.headings,
                    self.screen_grid):
            layout.addWidget(box)
        self.problem = QLabel("")
        self.problem.setStyleSheet("color: #c92a2a")
        layout.addWidget(self.problem)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._check)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _check(self) -> None:
        if self.changes() is None:
            return
        self.accept()

    def changes(self) -> Optional[dict]:
        area = parse_area(self.area.text())
        if area is False:
            self.problem.setText("The print area is not a range (e.g. A1:K40)")
            return None
        titles = parse_rows(self.titles.text())
        if titles is False:
            self.problem.setText("Rows to repeat are rows (e.g. 1:2)")
            return None
        return {"print_area": area, "titles": titles, "fit_width": self.fit.isChecked(),
                "center_h": self.center_h.isChecked(), "center_v": self.center_v.isChecked(),
                "print_gridlines": self.gridlines.isChecked(),
                "print_headings": self.headings.isChecked()}


def sheet_page_setup(window, index: int) -> None:
    item = _run_item(window, index)
    if item is None or item.sheet is None:
        window.status_hint.setText("This page is not a spreadsheet page")
        return
    dialog = SheetLayoutDialog(item.sheet, window)
    if not getattr(window, "interactive_prompts", True):
        window._last_data_dialog = dialog
        return
    if dialog.exec() != QDialog.Accepted:
        return
    apply_dialog(window, item, dialog)


def apply_dialog(window, item, dialog: SheetLayoutDialog) -> None:
    changes = dialog.changes()
    if changes is None:
        return
    sheet = item.sheet
    view = window.view
    view.begin_snapshot(item.run_frames())
    wb = sheet.workbook
    wb.set_page_options(sheet, **changes)
    if dialog.screen_grid.isChecked() != sheet.show_gridlines:
        sheet.show_gridlines = dialog.screen_grid.isChecked()
    item.relayout()
    item.update()
    view.commit_snapshot("Page layout")


# -- page breaks -----------------------------------------------------------------------------------------
def insert_break(window, item, row: int) -> None:
    """A manual break above *row* (Excel's Insert Page Break)."""
    if row <= 0:
        return
    breaks = sorted(set(options(item.sheet)["breaks"]) | {int(row)})
    change_options(window, item, "Insert page break", breaks=breaks)


def remove_break(window, item, row: int) -> None:
    breaks = [b for b in options(item.sheet)["breaks"] if b != int(row)]
    change_options(window, item, "Remove page break", breaks=breaks)


def reset_breaks(window, item) -> None:
    change_options(window, item, "Reset all page breaks", breaks=[])


def move_break(window, item, old: Optional[int], new: int) -> None:
    """A break dragged to another row: manual from now on (Excel)."""
    breaks = set(options(item.sheet)["breaks"])
    if old is not None:
        breaks.discard(int(old))
    if new > 0:
        breaks.add(int(new))
    change_options(window, item, "Move page break", breaks=sorted(breaks))


def set_print_area(window, item, area: Optional[list]) -> None:
    change_options(window, item, "Set print area" if area else "Clear print area",
                   print_area=list(area) if area else None)
