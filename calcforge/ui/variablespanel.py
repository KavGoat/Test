"""The Variables panel on the side rail (decision 21).

Every name the document's equations define, in the order SMath reads them:
its value and unit as the defining equation shows them, the page it is on
(and whether it is inside a self-contained block), and its error in red when
it has one. Clicking a row goes to the equation that defines it.

Below them, under Tables (the user's choice, 2026-10-10), what the tables
give the equations: each defined name (W_total) and each column a table's
headings name (Loads.Load), with its value; clicking one goes to its cells.

A name defined twice has two rows: SMath allows redefining, and which
definition an equation sees depends on where it is.

With calc section breaks (2026-10-11) the rows come section by section,
under a heading for each; a global one is marked, and right-click makes a
variable (or a table's cells) global or local again.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QHeaderView, QLabel, QLineEdit, QMenu, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

COLUMNS = ("Name", "Value", "Unit", "Page")
ERROR_RED = "#c92a2a"


@dataclass
class VariableRow:
    name: str
    value: str
    unit: str
    page: int                   # 1-based
    where: str                  # "Page 2", "Page 2 · block"
    error: str
    region_id: int
    source: str = "Equation"    # or "Measurement" (decision 24), or "Table"
    cells: Optional[tuple] = None   # a table's: (sheet name, (top, left, bottom, right))
    section: int = 1            # the calc section it is in (1-based)
    is_global: bool = False     # read by later sections too


def _split_value(shown: str) -> tuple:
    """ "12.5 kN" -> ("12.5", "kN") — the unit as plain text reads it."""
    from ..calc.record import plain_units

    number, _, unit = shown.partition(" ")
    if number.startswith("[") or number.startswith('"'):
        return shown, ""
    return number, plain_units(unit)


def variable_rows(document) -> list:
    """Every definition in the document, in reading order."""
    from ..calc.docsheet import sheet_for

    sheet = sheet_for(document)
    worksheet = sheet.worksheet
    pages = {page.uid: index for index, page in enumerate(document.pages)}
    rows = []
    sectioned = bool(sheet.section_starts())
    for region in worksheet.ordered():
        page_uid = sheet.page_uid(region)
        if page_uid not in pages or region.kind != "math":
            continue
        page = pages[page_uid] + 1
        where = f"Page {page}"
        if worksheet.scope_of.get(region.id) is not None:
            where += " · block"
        error = region.error.message if region.error is not None else ""
        fmt = region.fmt or worksheet.format
        source = getattr(region, "calcforge_source", "Equation")
        section = sheet.section_of(region) + 1 if sectioned else 1
        made = region.is_global
        if made:
            where += " · global"
        names = list(region.defined_vars.items())
        for name, value in names:
            shown, problem = _value_text(worksheet, region, value, fmt)
            number, unit = _split_value(shown)
            rows.append(VariableRow(name, number, unit, page, where, error or problem,
                                    region.id, source, None, section, made))
        for (name, arity), _body in region.defined_funcs.items():
            rows.append(VariableRow(f"{name}({', '.join(['·'] * arity)})", "function", "",
                                    page, where, error, region.id, source, None, section, made))
        if not names and not region.defined_funcs and error:
            name = _defined_name(region)
            if name:
                rows.append(VariableRow(name, "", "", page, where, error, region.id, source,
                                        None, section, made))
    return rows


def table_rows(document) -> list:
    """What the tables give the equations: defined names, then each table's
    columns by heading, with their values."""
    from ..sheet import formula as F
    from ..sheet.docbook import _ident, book_for
    from ..sheet.evaluate import Ctx, RefValue, ev, result
    from ..sheet.numfmt import format_value
    from ..sheet.values import Array, ErrorValue, Qty, SheetError

    book = book_for(document)
    wb = book.workbook
    pages = {page.uid: index for index, page in enumerate(document.pages)}
    calc = book._calc()
    sectioned = bool(calc.section_starts())

    def placed(sheet, cells) -> dict:
        """The section a table is in, and whether these of its cells are global."""
        if not sectioned or sheet is None:
            return {}
        out = {"section": calc.section_of_key(book._key(sheet)) + 1}
        if cells is not None:
            out["is_global"] = book._within(cells[1], (sheet.page or {}).get("global_cells") or [])
        return out
    homes = {}
    for uid, sheet in book.by_uid.items():
        place = book._places.get(uid)
        if place is not None and place[0] in pages:
            homes[sheet.id] = pages[place[0]] + 1

    from ..sheet.values import BLANK

    def shown(values: list) -> tuple:
        values = [v for v in values if v is not BLANK and v != ""]
        texts, units, error = [], set(), ""
        for v in values[:4]:
            if isinstance(v, ErrorValue):
                error = v.code
                break
            if isinstance(v, Qty):
                text = format_value(v).text
                number, _, unit = text.partition(" ")
                texts.append(number)
                units.add(unit)
            else:
                texts.append(format_value(v).text)
        text = ", ".join(texts) + ("…" if len(values) > 4 else "")
        return text, (units.pop() if len(units) == 1 else ""), error

    rows = []
    for (lower, scope), dn in sorted(wb.names.items(), key=lambda kv: kv[1].name.lower()):
        home = wb.sheet_by_id(scope) if scope else None
        try:
            got = ev(F.parse(dn.refers_to).tree, Ctx(wb, home or (wb.sheets[0] if wb.sheets else None), 0, 0))
        except (F.FormulaError, SheetError, AttributeError) as e:
            got = getattr(e, "error", ErrorValue("#NAME?"))
        cells = None
        sheet = None
        if isinstance(got, RefValue):
            sheet = got.sheet
            cells = (sheet.name, (got.top, got.left, got.bottom, got.right))
            got = got.value_at(0, 0) if got.single else got.to_array()
        elif not isinstance(got, Array):
            got = result(got)                  # a LAMBDA name: #CALC!, as in a cell
        values = list(got.values()) if isinstance(got, Array) else [got]
        text, unit, error = shown(values)
        page = homes.get(sheet.id, 0) if sheet is not None else 0
        name = dn.name + (f" ({home.name})" if home is not None else "")
        rows.append(VariableRow(name, text, unit, page, f"Page {page}" if page else "",
                                error, -1, "Table", cells, **placed(sheet, cells)))
    for sheet in wb.sheets:
        if sheet.kind != "table" or not sheet.size:
            continue
        height = sheet.size[0]
        for (row, col), cell in sorted(sheet.cells.items()):
            if row != 0 or not isinstance(cell.value, str) or not _ident(cell.value):
                continue
            values = [sheet.cells[(r, col)].value for r in range(1, height)
                      if (r, col) in sheet.cells]
            text, unit, error = shown(values)
            page = homes.get(sheet.id, 0)
            cells = (sheet.name, (1, col, max(1, height - 1), col))
            rows.append(VariableRow(f"{sheet.name}.{_ident(cell.value)}", text, unit, page,
                                    f"Page {page}" if page else "", error, -1, "Table",
                                    cells, **placed(sheet, cells)))
    return rows


def _value_text(worksheet, region, value, fmt) -> tuple:
    """(the value as the equation would show it, an error if it has one). A
    definition SMath keeps unevaluated (it uses a name that is only a unit
    until defined, 12.5'kN*m) is evaluated as it would be where it is."""
    from ..calc.engine.display import display_text, display_value
    from ..calc.engine.evaluator import Lazy

    try:
        if isinstance(value, Lazy):
            value = worksheet.evaluator.eval(value.node, worksheet._context_before(region))
        return display_text(display_value(value, fmt)) or "", ""
    except Exception as exc:                          # noqa: BLE001  (shown as it can be)
        return "", getattr(exc, "message", "") or "cannot be evaluated"


def _defined_name(region) -> Optional[str]:
    """The name a definition that failed was meant to define ("y" of y≔z+1)."""
    from ..calc.engine.model import to_text

    try:
        text = to_text(region.editor.root)
    except Exception:                                  # noqa: BLE001
        return None
    if "≔" not in text:
        return None
    name = text.split("≔", 1)[0].strip()
    return name if name and "(" not in name else None


class VariablesPanel(QWidget):
    """The document's variables, as a list to look things up in."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("variablesPanel")
        self.rows: list = []
        self._watched = None
        self._watched_book = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Find a variable")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _t: self._fill())
        lay.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(list(COLUMNS))
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        header = self.tree.header()
        # Name and Value share what is left after Unit and Page, so the
        # table fits the panel at any width instead of scrolling sideways
        header.setMinimumSectionSize(30)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemClicked.connect(lambda node, _col: self.go_to(node))
        self.tree.itemActivated.connect(lambda node, _col: self.go_to(node))
        lay.addWidget(self.tree, 1)
        self.empty = QLabel("No variables yet: define one with  name : value  in an equation.")
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet("color:#6b7280;")
        lay.addWidget(self.empty)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.refresh)

    # -- keeping up -----------------------------------------------------------------
    def watch(self, document) -> None:
        """Follow *document*'s calculations (the window's document can change)."""
        from ..calc.docsheet import sheet_for

        sheet = sheet_for(document)
        if self._watched is sheet:
            return
        if self._watched is not None and self._soon in self._watched.listeners:
            self._watched.listeners.remove(self._soon)
        self._watched = sheet
        sheet.listeners.append(self._soon)
        from ..sheet.docbook import book_for
        # the tables of the document left behind are not followed either: a
        # closed document's book held on to this panel, and the panel to its
        # window
        old = self._watched_book
        if old is not None and self._soon_for_tables in old.listeners:
            old.listeners.remove(self._soon_for_tables)
        book = book_for(document)
        self._watched_book = book
        if self._soon_for_tables not in book.listeners:
            book.listeners.append(self._soon_for_tables)
        self._soon()

    def _soon_for_tables(self, _keys=None) -> None:
        self._timer.start()

    def _soon(self) -> None:
        self._timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._soon()

    def refresh(self) -> None:
        document = self.window.document
        self.watch(document)
        self.rows = variable_rows(document)
        self.table_start = len(self.rows)
        try:
            self.rows += table_rows(document)
        except Exception:  # noqa: BLE001  (the list of equations still shows)
            pass
        self._fill()

    def _heading(self, text: str, tip: str, colour: Optional[str] = None) -> None:
        head = QTreeWidgetItem([text, "", "", ""])
        font = head.font(0)
        font.setBold(True)
        head.setFont(0, font)
        head.setFlags(Qt.ItemIsEnabled)
        head.setToolTip(0, tip)
        if colour:
            head.setForeground(0, QBrush(QColor(colour)))
        self.tree.addTopLevelItem(head)
        head.setFirstColumnSpanned(True)          # the heading across the whole row

    def _fill(self) -> None:
        from .calcsections import BAND, has_sections, sections
        wanted = self.filter.text().strip().lower()
        self.tree.clear()
        document = self.window.document
        listed = sections(document) if has_sections(document) else []
        headed = False
        section_shown = None
        for index, row in enumerate(self.rows):
            if wanted and wanted not in row.name.lower():
                continue
            if row.source == "Table" and not headed:
                headed = True
                section_shown = None
                self._heading("Tables", "What the tables give the equations: named cells, and "
                                        "Table.Column for each heading")
            if listed and row.section != section_shown and row.section <= len(listed):
                section_shown = row.section
                part = listed[row.section - 1]
                self._heading(part.label if row.source != "Table" else f"  {part.label}",
                              "A calc section: what is defined in it is not seen after the next "
                              "break, unless it is global", BAND.name())
            node = QTreeWidgetItem([("🌐 " if row.is_global else "") + row.name,
                                    row.error or row.value, row.unit, row.where])
            node.setData(0, Qt.UserRole, index)
            tip = f"{row.name} — {row.source.lower()} on page {row.page}" if row.page else row.name
            if row.error:
                for column in range(len(COLUMNS)):
                    node.setForeground(column, QBrush(QColor(ERROR_RED)))
                tip += f"\n{row.error}"
            for column in range(len(COLUMNS)):
                node.setToolTip(column, tip)
            self.tree.addTopLevelItem(node)
        self.empty.setVisible(not self.rows)

    # -- global or not (calc sections) ------------------------------------------------------
    def _menu(self, pos) -> None:
        row = self.row_of(self.tree.itemAt(pos))
        if row is None:
            return
        menu = QMenu(self)
        menu.addAction("Go to", lambda: self.go_to(self.tree.itemAt(pos)))
        if row.source != "Measurement":
            act = menu.addAction("Make Local" if row.is_global else "Make Global",
                                 lambda: self.set_global(row, not row.is_global))
            act.setToolTip("A global variable or cell is read by every later calc section")
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def set_global(self, row: VariableRow, on: bool) -> None:
        """Make a variable's equation, or a table's cells, global (or not)."""
        window = self.window
        if row.cells is not None:
            tables = window.view.tables
            target = next((t for t in tables._all_tables()
                           if t.sheet is not None and t.sheet.name == row.cells[0]), None)
            if target is not None:
                from .calcsections import set_cells_global
                set_cells_global(window, target, row.cells[1], on)
        else:
            item = self.item_for(row.region_id)
            if item is None or getattr(item, "region", None) is None:
                return
            from .calcmenu import change
            change(window, [item], "Make global" if on else "Make local",
                   lambda r: setattr(r, "is_global", bool(on)))
        self.refresh()

    # -- going to one ---------------------------------------------------------------
    def row_of(self, node) -> Optional[VariableRow]:
        index = node.data(0, Qt.UserRole) if node is not None else None
        return self.rows[index] if index is not None and 0 <= index < len(self.rows) else None

    def go_to(self, node) -> None:
        row = self.row_of(node)
        if row is None:
            return
        if row.cells is not None:
            self._go_to_cells(*row.cells)
            return
        item = self.item_for(row.region_id)
        if item is None:
            return
        window = self.window
        window.view.calc.leave()
        window.go_to_page(row.page - 1)
        scene = window.view.scene()
        scene.clearSelection()
        item.setSelected(True)
        window.view.centerOn(item)
        window.refresh_selection()

    def _go_to_cells(self, sheet_name: str, block: tuple) -> None:
        """Open the table (or spreadsheet page) and pick out the cells."""
        tables = self.window.view.tables
        target = next((t for t in tables._all_tables()
                       if t.sheet is not None and t.sheet.name == sheet_name), None)
        if target is None:
            return
        self.window.view.calc.leave()
        tables.open(target, block[:2])
        tables.select(block[:2], block[2:], block[:2])
        self.window.view.centerOn(target.mapToScene(target.block_rect(*block).center()))

    def item_for(self, region_id: int):
        from ..calc.docsheet import sheet_for

        found = getattr(sheet_for(self.window.document), "items", {}).get(region_id)
        if found is not None:
            return found
        for page in self.window.document.pages:        # a measurement's variable
            if page.frame is None:
                continue
            for item in page.frame.markups():
                if getattr(item, "variable_region_id", None) == region_id:
                    return item
        return None
