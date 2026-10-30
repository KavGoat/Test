"""A spreadsheet's page layout: Excel's Page Layout options for a run of
spreadsheet pages (items/sheetpage.py, sheet/pagination.py).

Fit to page width, Print Area, Print Titles, centring, printed gridlines and
headings, and the manual page breaks (Insert / Remove Page Break, Reset All
Page Breaks). Each change is one undo step.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QSpinBox, QVBoxLayout)

from ..sheet.pagination import options
from ..sheet.refs import CellRef, area_text, col_letters, parse_range


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
    run = getattr(item, "run_frames", None)
    view.begin_snapshot(run() if run is not None else view.involved_frames(item))
    sheet.workbook.set_page_options(sheet, **changes)
    if run is not None:
        item.relayout()
        if _fit_run(window, item, 0, label):
            return
    view.commit_snapshot(label)


def _spare_pages(item) -> int:
    """Pages the run has beyond what its cells and breaks need — ones the
    user added, kept whatever the layout does."""
    from ..sheet.pagination import pages_needed
    frames = item.run_frames()
    if not frames:
        return 0
    return max(0, len(frames) - pages_needed(item.sheet, frames[0].page.setup))


def _fit_run(window, item, spare: int, label: str) -> bool:
    """The run's pages as many as its rows, print area and breaks need: a
    break removed takes back the page it made (the user, 2026-10-15: "new
    surprise rows get added"), a print area has its pages and no others
    (2026-10-17), and a page added by hand added the rows it holds. Only
    empty pages at the run's end go; all in the same undo step as the
    change. True when pages changed."""
    from ..items.sheetpage import SheetRunItem
    from ..sheet.pagination import pages_needed
    from . import sheetpages
    frames = item.run_frames()
    if not frames or not hasattr(window, "_structure_snapshot"):
        return False
    target = max(1, pages_needed(item.sheet, frames[0].page.setup) + spare)
    going = []
    for frame in reversed(frames[target:]):
        if any(not isinstance(m, SheetRunItem) for m in frame.markups()):
            break                               # something drawn on it: it stays
        going.append(frame)
    adding = max(0, target - len(frames))
    if not going and not adding:
        return False
    view = window.view
    before = window._structure_snapshot()
    by_uid = {entry["uid"]: entry for entry in before["pages"]}
    for frame, items in (view._snapshot or []):
        entry = by_uid.get(frame.page.uid)
        if entry is not None:
            entry["items"] = items
    view._snapshot = []
    if adding:
        sheetpages.add_run_pages(window, [(item, adding)])
    else:
        document = window.document
        for frame in going:
            document.remove_page(document.index_of(frame.page))
        window.rebuild_scenes()
    window.record_structure_change(before, label)
    view.documentEdited.emit()
    return True


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


def parse_cols(text: str) -> Optional[list]:
    """"A:B" or "$A:$B" or "C" → [first, last] columns; "" → None; nonsense → False."""
    from ..sheet.refs import col_index
    text = (text or "").strip().replace("$", "").upper()
    if not text:
        return None
    a, _, b = text.partition(":")
    b = b or a
    if not (a.isalpha() and b.isalpha() and len(a) <= 3 and len(b) <= 3):
        return False
    first, last = sorted((col_index(a), col_index(b)))
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
        cols = opts.get("title_cols")
        self.title_cols = QLineEdit(f"${col_letters(cols[0])}:${col_letters(cols[1])}" if cols else "")
        self.title_cols.setPlaceholderText("e.g. A:B")
        form.addRow("Columns to repeat at left:", self.title_cols)
        layout.addLayout(form)
        # Excel's Scaling: Adjust to N% normal size, or Fit to 1 page wide by N tall
        self.scale = QSpinBox()
        self.scale.setRange(10, 400)
        self.scale.setSuffix("% normal size")
        self.scale.setValue(int(opts.get("scale") or 100))
        form.addRow("Adjust to:", self.scale)
        fit_wide = int(opts["fit_width"] or 0)
        self.fit = QCheckBox("Fit to")
        self.fit.setChecked(bool(fit_wide))
        self.wide = QSpinBox()
        self.wide.setRange(1, 99)
        self.wide.setSuffix(" page(s) wide")
        self.wide.setValue(max(1, fit_wide))
        self.tall = QSpinBox()
        self.tall.setRange(0, 999)
        self.tall.setSpecialValueText("as many pages as it takes, tall")
        self.tall.setSuffix(" page(s) tall")
        self.tall.setValue(int(opts.get("fit_tall") or 0))
        self.fit.toggled.connect(self._fitting)
        self.tall.valueChanged.connect(self._fitting)
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
        wide = QHBoxLayout()
        wide.addWidget(self.fit)
        wide.addWidget(self.wide)
        wide.addStretch(1)
        layout.addLayout(wide)
        tall = QHBoxLayout()
        tall.addSpacing(20)
        tall.addWidget(QLabel("by"))
        tall.addWidget(self.tall)
        tall.addStretch(1)
        layout.addLayout(tall)
        self._fitting()
        for box in (self.center_h, self.center_v, self.gridlines, self.headings,
                    self.screen_grid):
            layout.addWidget(box)
        self.problem = QLabel("")
        self.problem.setStyleSheet("color: #c92a2a")
        layout.addWidget(self.problem)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._check)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _fitting(self, *_args) -> None:
        """Fitting to pages sets the size, as in Excel: Adjust to is unused."""
        self.scale.setEnabled(not (self.fit.isChecked() or self.tall.value()))
        self.wide.setEnabled(self.fit.isChecked())

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
        title_cols = parse_cols(self.title_cols.text())
        if title_cols is False:
            self.problem.setText("Columns to repeat are columns (e.g. A:B)")
            return None
        return {"print_area": area, "titles": titles, "title_cols": title_cols,
                "fit_width": self.wide.value() if self.fit.isChecked() else False,
                "fit_tall": self.tall.value(), "scale": self.scale.value(),
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
    accepted = dialog.exec() == QDialog.Accepted
    if accepted:
        apply_dialog(window, item, dialog)
    from .release import done_with
    done_with(dialog)


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
def insert_break(window, item, row: int, col: int = 0) -> None:
    """Excel's Insert Page Break at the active cell: a break above its row
    and one left of its column (only the one in row 1 or column A)."""
    opts = options(item.sheet)
    changes = {}
    if row > 0:
        changes["breaks"] = sorted(set(opts["breaks"]) | {int(row)})
    if col > 0:
        changes["col_breaks"] = sorted(set(opts.get("col_breaks") or []) | {int(col)})
    if changes:
        change_options(window, item, "Insert page break", **changes)


def remove_break(window, item, row: int, col: int = 0) -> None:
    """Excel's Remove Page Break: the breaks at the active cell's top and left."""
    opts = options(item.sheet)
    changes = {"breaks": [b for b in opts["breaks"] if b != int(row)],
               "col_breaks": [c for c in opts.get("col_breaks") or [] if c != int(col)]}
    change_options(window, item, "Remove page break", **changes)


def has_break(item, row: int, col: int) -> bool:
    opts = options(item.sheet)
    return (row > 0 and row in opts["breaks"]) or (col > 0 and col in (opts.get("col_breaks") or []))


def reset_breaks(window, item) -> None:
    change_options(window, item, "Reset all page breaks", breaks=[], col_breaks=[])


def move_break(window, item, old: Optional[int], new: int, across: bool = False) -> None:
    """A break dragged to another row (or, *across*, column): manual from now on (Excel)."""
    key = "col_breaks" if across else "breaks"
    breaks = set(options(item.sheet).get(key) or [])
    if old is not None:
        breaks.discard(int(old))
    if new > 0:
        breaks.add(int(new))
    change_options(window, item, "Move page break", **{key: sorted(breaks)})


def set_print_area(window, item, area: Optional[list]) -> None:
    change_options(window, item, "Set print area" if area else "Clear print area",
                   print_area=list(area) if area else None)
