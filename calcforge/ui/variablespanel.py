"""The Variables panel on the side rail (decision 21).

Every name the document's equations define, in the order SMath reads them:
its value and unit as the defining equation shows them, the page it is on,
and its error in red when it has one. Clicking a row goes to the equation
that defines it. Each calculation block and each imported workbook is a
section of its own where it comes in that order (the user, 2026-10-24:
"each block should show as its own section", and a block after a workbook
was listed before it), its heading saying whether it is self-contained. A
workbook's section holds what the equations read of it — its CalcForge
variables (cells named in their Variable box, read bare anywhere) and, one
that isn't self-contained, its Excel names as they are dialled in
(Seismic_Actions_NZS1170_5.Z, a sheet's own Tables.ReturnPeriodFactor) —
and, one that is self-contained, its Excel names greyed under "Its own
cells only", for reference (their pick, 2026-10-24).

After them, under Tables (the user's choice, 2026-10-10), what the tables
give the equations: each defined name (W_total) and each column a table's
headings name (Loads.Load), with its value; clicking one goes to its cells.

A group with nothing in it is not shown; closed to start, every group opens
while finding a variable. A name Excel itself has as #REF! (its cells
deleted in Excel) is not listed.

A name defined twice has two rows: SMath allows redefining, and which
definition an equation sees depends on where it is — the latest one before
it in reading order, whether an equation, a measurement or a table defines
it (the user's report, 2026-10-17). The one in force at the selected
equation (at the end of the document when none is selected) is bold.

With calc section breaks (2026-10-11) the rows come section by section,
under a heading for each; a global one is marked, and right-click makes a
variable (or a table's cells) global or local again.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QHeaderView, QLabel, QLineEdit, QMenu, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

COLUMNS = ("Name", "Value", "Unit", "Page")
GROUP_ROLE = Qt.UserRole + 1         # a group heading's key ("blocks", "book:Name"…)
ERROR_RED = "#c92a2a"
CLOSED_GREY = "#8c8c8c"            # a self-contained workbook's own name, for reference


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
    key: Optional[tuple] = None  # where it is defined in reading order
    group: str = ""             # the workbook it is under (its name), for its heading
    sheet_name: bool = False    # a spreadsheet's own name (Define Name), not a Variable box's
    group_contained: bool = False   # that workbook is self-contained
    block: str = ""             # the calculation block it is in (its uid)
    block_label: str = ""       # "Block 2", numbered in reading order
    block_contained: bool = False   # that block is self-contained
    # a self-contained workbook's own Excel name: listed (greyed) for
    # reference, read only by its own cells (the user, 2026-10-24)
    closed: bool = False
    # its workbook's place in reading order (its first page), and that page:
    # the workbook is a section where it comes (the user, 2026-10-24)
    order: Optional[tuple] = None
    group_page: int = 0


def _gone(row) -> bool:
    """A spreadsheet's name whose cells were deleted in Excel (#REF! there too):
    nothing an equation can use."""
    return row.sheet_name and "#REF!" in (row.error or "")


def _split_value(shown: str) -> tuple:
    """ "12.5 kN" -> ("12.5", "kN") — the unit as plain text reads it."""
    from ..calc.record import plain_units

    number, _, unit = shown.partition(" ")
    if number.startswith("[") or number.startswith('"'):
        return shown, ""
    return number, plain_units(unit)


def block_labels(sheet, pages: dict) -> dict:
    """Each calculation block's name in the panel: block uid -> "Block 2",
    numbered in reading order (page, then down, then across)."""
    placed = []
    for uid, (page_uid, (left, top, _right, _bottom), _on, _out) in sheet.blocks.items():
        if page_uid in pages:
            placed.append((pages[page_uid], top, left, uid))
    return {uid: f"Block {k}" for k, (_p, _t, _l, uid) in enumerate(sorted(placed), 1)}


def variable_rows(document) -> list:
    """Every definition in the document, in reading order."""
    from ..calc.docsheet import sheet_for

    sheet = sheet_for(document)
    worksheet = sheet.worksheet
    pages = {page.uid: index for index, page in enumerate(document.pages)}
    rows = []
    sectioned = bool(sheet.section_starts())
    labels = block_labels(sheet, pages)
    for region in worksheet.ordered():
        page_uid = sheet.page_uid(region)
        if page_uid not in pages or region.kind != "math":
            continue
        page = pages[page_uid] + 1
        where = f"Page {page}"           # a block's heading says it is in one
        error = region.error.message if region.error is not None else ""
        fmt = region.fmt or worksheet.format
        source = getattr(region, "calcforge_source", "Equation")
        section = sheet.section_of(region) + 1 if sectioned else 1
        made = region.is_global
        if made:
            where += " · global"
        block = sheet.block_of(region) or ""
        inside = {"block": block, "block_label": labels.get(block, "Block") if block else "",
                  "block_contained": bool(block and sheet.blocks[block][2])}
        names = list(region.defined_vars.items())
        for name, value in names:
            shown, problem = _value_text(worksheet, region, value, fmt)
            number, unit = _split_value(shown)
            rows.append(VariableRow(name, number, unit, page, where, error or problem,
                                    region.id, source, None, section, made, region.key,
                                    **inside))
        for (name, arity), _body in region.defined_funcs.items():
            rows.append(VariableRow(f"{name}({', '.join(['·'] * arity)})", "function", "",
                                    page, where, error, region.id, source, None, section, made,
                                    **inside))
        if not names and not region.defined_funcs and error:
            name = _defined_name(region)
            if name:
                rows.append(VariableRow(name, "", "", page, where, error, region.id, source,
                                        None, section, made, **inside))
    return rows


def table_rows(document) -> list:
    """What the tables give the equations: defined names, then each table's
    columns by heading, with their values."""
    from ..sheet import formula as F
    from ..sheet.docbook import _ident, book_for
    from ..sheet.evaluate import Ctx, RefValue, ev, result
    from ..sheet.numfmt import format_value
    from ..sheet.values import Array, ErrorValue, Qty, SheetError

    docbook = book_for(document)
    wb = docbook.workbook
    book_key = docbook._key
    pages = {page.uid: index for index, page in enumerate(document.pages)}
    calc = docbook._calc()
    sectioned = bool(calc.section_starts())

    def placed(sheet, cells) -> dict:
        """The section a table is in, and whether these of its cells are global."""
        if not sectioned or sheet is None:
            return {}
        out = {"section": calc.section_of_key(book_key(sheet)) + 1}
        if cells is not None:
            out["is_global"] = docbook._within(cells[1], (sheet.page or {}).get("global_cells") or [])
        return out
    homes = {}
    for uid, sheet in docbook.by_uid.items():
        place = docbook._places.get(uid)
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

    from ..sheet.docbook import sheet_ident

    firsts = {}                       # workbook id -> (reading key, page) of its first page
    for sheet in wb.sheets:
        if sheet.book and sheet.id in homes:
            at = book_key(sheet)
            if sheet.book not in firsts or at < firsts[sheet.book][0]:
                firsts[sheet.book] = (at, homes[sheet.id])
    rows, own = [], []
    for (lower, scope), dn in sorted(wb.names.items(), key=lambda kv: kv[1].name.lower()):
        home = wb.sheet_by_id(scope) if isinstance(scope, int) else None
        book = wb.books.get(scope) if isinstance(scope, str) else \
            (wb.books.get(home.book) if home is not None and home.book else None)
        closed = book is not None and book.self_contained and not dn.variable
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
        group, contained, book_id = "", False, book.id if book is not None else None
        if dn.variable and sheet is not None and sheet.book in wb.books:
            # a CalcForge variable on a workbook's cells: under its workbook
            # (the user, 2026-10-24), read bare all the same
            group, contained = wb.books[sheet.book].name, wb.books[sheet.book].self_contained
            book_id = sheet.book
        elif closed:
            # its Excel names are its own cells', not the equations': shown
            # as Excel shows them, the sheet's own with the sheet
            group, contained = book.name, True
        elif book is not None and home is not None:
            name = f"{sheet_ident(home.name)}.{dn.name}"     # a sheet's own name: Sheet.Name
            group = book.name
        elif book is not None:
            name = f"{book.name}.{dn.name}"                  # the workbook's: Book.Name
            group = book.name
        elif book is None and home is None and not dn.variable:
            if docbook.closed(docbook._kept_on(dn)):
                continue                                     # kept with a self-contained workbook
            written = docbook.written_as(dn)
            if written:
                name = written                               # a spreadsheet's own: Sheet.Name
        made = VariableRow(name, text, unit, page, f"Page {page}" if page else "",
                           error, -1, "Workbook" if group else "Table", cells,
                           **placed(sheet, cells),
                           key=book_key(sheet) if sheet is not None and not closed else None,
                           group=group, sheet_name=not dn.variable, group_contained=contained,
                           closed=closed)
        if group:
            made.order, made.group_page = firsts.get(book_id, (None, 0))
        (own if group else rows).append(made)
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
                                    cells, **placed(sheet, cells), key=book_key(sheet)))
    # under each workbook: its CalcForge variables, and (one that isn't
    # self-contained) its Excel names as dialled in
    return rows + sorted(own, key=lambda r: (r.group.lower(), r.sheet_name, r.name.lower()))


def in_force(document, rows: list, region=None) -> dict:
    """For each name defined more than once: the index in *rows* of the
    definition in force at *region* — what an equation just after it would
    read (its own definition included), by the evaluator's own rule
    (IndexedContext.entry) — or at the end of the document when *region* is
    None. A name nothing there reads is left out."""
    from ..calc.docsheet import sheet_for
    from ..calc.engine import evaluator
    from ..calc.engine.evaluator import TABLES, IndexedContext
    from ..calc.worksheet import ScopedContext

    worksheet = sheet_for(document).worksheet
    by_name: dict = {}
    for index, row in enumerate(rows):
        if row.key is not None and "(" not in row.name:
            by_name.setdefault(row.name, []).append(index)
    twice = {name: found for name, found in by_name.items() if len(found) > 1}
    if not twice:
        return {}
    evaluator.EXTERNAL = worksheet.external          # this document's tables
    if region is not None and region in worksheet.regions:
        y, x, rid = region.key
        just_after = (y, x, rid + 0.5)
        scope = worksheet.scope_of.get(region.id)
        ctx = ScopedContext(worksheet.index, just_after, worksheet._scoped.get(scope)) \
            if scope is not None else IndexedContext(worksheet.index, just_after)
    else:
        ctx = IndexedContext(worksheet.index, (float("inf"),))
    out = {}
    for name, found in twice.items():
        entry = ctx.entry(name)
        if entry is None:
            continue
        table = entry[1] is TABLES
        for index in found:
            row = rows[index]
            # a cell's name, a table's or a workbook's (listed under its
            # workbook), against an equation's or a measurement's
            cells = row.source in ("Table", "Workbook")
            if cells == table and tuple(row.key) == tuple(entry[0]):
                out[name] = index
                break
    return out


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
        self.opened: set = set()        # the groups shown open (their keys)
        self._finding = False
        self._filling = False
        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(list(COLUMNS))
        self.tree.setRootIsDecorated(True)      # the groups' arrows
        self.tree.setIndentation(14)
        self.tree.itemExpanded.connect(lambda node: self._expanded(node, True))
        self.tree.itemCollapsed.connect(lambda node: self._expanded(node, False))
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        header = self.tree.header()
        # Name and Value share what is left after Unit and Page, so the
        # table fits the panel at any width instead of scrolling sideways
        header.setMinimumSectionSize(30)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        # Value takes what it needs up to a third: Name has the rest, so a
        # name three groups deep still shows (an even share left "sha…" and,
        # in a narrow panel, nothing at all of a workbook's names)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tree.installEventFilter(self)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemClicked.connect(lambda node, _col: self.go_to(node))
        self.tree.itemActivated.connect(lambda node, _col: self.go_to(node))
        lay.addWidget(self.tree, 1)
        # what the bold rows mean, shown while a name is defined more than once
        self.in_force_note = QLabel()
        self.in_force_note.setWordWrap(True)
        self.in_force_note.setStyleSheet("color:#6b7280;")
        self.in_force_note.hide()
        lay.addWidget(self.in_force_note)
        self.empty = QLabel("No variables yet: define one with  name : value  in an equation.")
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet("color:#6b7280;")
        lay.addWidget(self.empty)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._refresh_if_shown)
        self._stale = False

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

    def _refresh_if_shown(self) -> None:
        """Brought up to date when it can be seen; hidden, when it is shown
        (every value typed into a big workbook rebuilt it unseen, a fifth of
        the time the edit took, 2026-10-19)."""
        if self.isVisible():
            self._stale = False
            self.refresh()
        else:
            self._stale = True

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

    def _heading(self, text: str, tip: str, colour: Optional[str] = None, parent=None):
        """A heading row: bold, across the whole row. Made with its parent
        (the tree or a group), which owns it: one made alone and added was
        freed twice when the tree was cleared, a crash."""
        head = QTreeWidgetItem(self.tree if parent is None else parent, [text, "", "", ""])
        font = head.font(0)
        font.setBold(True)
        head.setFont(0, font)
        head.setFlags(Qt.ItemIsEnabled)
        head.setToolTip(0, tip)
        if colour:
            head.setForeground(0, QBrush(QColor(colour)))
        head.setFirstColumnSpanned(True)          # the heading across the whole row
        return head

    def _group(self, parent, key: str, text: str, tip: str):
        """A group to open (▸) and close: Blocks or Workbooks, their
        Self-contained and Not self-contained, and each block or workbook
        (the user, 2026-10-24). Closed to start; open while finding."""
        head = self._heading(text, tip + " · click to show or hide", parent=parent)
        head.setData(0, GROUP_ROLE, key)
        head.setExpanded(key in self.opened or self._finding)
        return head

    # -- which definition is in force -----------------------------------------------------
    def reading_point(self):
        """The equation the bold rows are for: the one being typed in, or the
        one picked on the page; None (the end of the document) otherwise."""
        from ..items.calc import CalcItem

        view = self.window.view
        item = getattr(getattr(view, "calc", None), "item", None)
        if item is None and view.scene() is not None:
            picked = [i for i in view.scene().selectedItems()
                      if isinstance(i, CalcItem) and getattr(i, "region", None) is not None]
            item = picked[0] if len(picked) == 1 else None
        return getattr(item, "region", None) if item is not None else None

    def selection_changed(self) -> None:
        """Another equation picked: the bold rows follow it."""
        if self.isVisible() and self.rows:
            self._mark_in_force()

    def _mark_in_force(self) -> None:
        region = self.reading_point()
        try:
            force = in_force(self.window.document, self.rows, region)
        except Exception:  # noqa: BLE001  (the list itself still shows)
            force = {}
        where = "the selected equation" if region is not None else "the end of the document"
        chosen = set(force.values())
        from PySide6.QtGui import QPalette
        accent = self.palette().color(QPalette.Link)       # the theme's accent, both themes
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        found = QTreeWidgetItemIterator(self.tree)
        while found.value() is not None:
            node = found.value()
            found += 1
            i = node.data(0, Qt.UserRole)
            if i is None:
                continue
            row = self.rows[i]
            font = node.font(0)
            font.setBold(i in chosen)
            node.setFont(0, font)
            if not row.error and not row.closed:
                # in force: bold in the accent colour (a heading is bold in the ink)
                node.setData(0, Qt.ForegroundRole, QBrush(accent) if i in chosen else None)
            tip = node.data(1, Qt.UserRole) or ""
            if row.name in force:
                if i in chosen:
                    tip += f"\nIn force at {where}."
                else:
                    other = self.rows[force[row.name]]
                    if tuple(row.key) < tuple(other.key):
                        tip += (f"\nNot in force at {where}: replaced by the "
                                f"{other.source.lower()} on page {other.page}.")
                    else:
                        tip += f"\nNot in force at {where}."
            for column in range(len(COLUMNS)):
                node.setToolTip(column, tip)
        upto = "up to it" if region is not None else "in the document"
        self.in_force_note.setText(f"Bold blue: the definition in force at {where} (the "
                                   f"latest {upto}, page by page, top to bottom).")
        self.in_force_note.setVisible(bool(force))

    def _clear(self) -> None:
        """Every row away. The groups are shut first and the rows taken out
        and dropped from the top: clear() with open groups crashed now and
        then (Qt kept the open rows' places while they went)."""
        tree = self.tree
        tree.setCurrentItem(None)
        tree.collapseAll()
        root = tree.invisibleRootItem()
        for gone in root.takeChildren():
            del gone

    def _row_node(self, parent, index: int, row: VariableRow):
        node = QTreeWidgetItem(self.tree if parent is None else parent,
                               [("🌐 " if row.is_global else "") + row.name,
                                row.error or row.value, row.unit, row.where])
        node.setData(0, Qt.UserRole, index)
        tip = f"{row.name} — {row.source.lower()} on page {row.page}" if row.page else row.name
        if row.closed:
            # for reference: no equation reads it (the user, 2026-10-24: greyed)
            for column in range(len(COLUMNS)):
                node.setForeground(column, QBrush(QColor(CLOSED_GREY)))
            tip += (f"\nOnly {row.group}'s own cells read it: the workbook is self-contained "
                    f"(untick Self-contained on its sheet tab to dial in to it)")
        if row.error:
            for column in range(len(COLUMNS)):
                node.setForeground(column, QBrush(QColor(ERROR_RED)))
            tip += f"\n{row.error}"
        for column in range(len(COLUMNS)):
            node.setToolTip(column, tip)
        node.setData(1, Qt.UserRole, tip)
        return node

    def _fill(self) -> None:
        """The rows in the document's reading order (by calc section), the
        tables' after them. Each calculation block and each imported
        workbook is a section of its own where it comes (the user,
        2026-10-24: "each block should show as its own section", and a
        block after a workbook was listed before it), its heading saying
        whether it is self-contained. A workbook's section holds what the
        equations read of it — its CalcForge variables and, one that isn't
        self-contained, its Excel names as dialled in — and, one that is
        self-contained, its Excel names greyed under "Its own cells only",
        for reference. Every section is closed until clicked, and one with
        nothing in it is not shown."""
        from .calcsections import BAND, has_sections, sections
        wanted = self.filter.text().strip().lower()
        self._finding = bool(wanted)
        current = self.tree.currentItem()
        current = current.data(0, Qt.UserRole) if current is not None else None
        self._filling = True
        self._clear()
        document = self.window.document
        listed = sections(document) if has_sections(document) else []
        listed_rows = [(index, row) for index, row in enumerate(self.rows)
                       if not (wanted and wanted not in row.name.lower()) and not _gone(row)]
        main, in_books = [], {}
        counts: dict = {}
        for index, row in listed_rows:
            if row.group:
                in_books.setdefault(row.group, []).append((index, row))
            else:
                main.append((index, row))
                if row.block:
                    counts[row.block] = counts.get(row.block, 0) + 1
        last = (float("inf"),)
        books = sorted(in_books.items(),
                       key=lambda kv: (tuple(kv[1][0][1].order or last), kv[0].lower()))

        def names(n: int) -> str:
            return f"{n} name{'s' * (n != 1)}"

        nodes = {}
        state = {"tables": False, "section": None}

        def section_of(row) -> None:
            """The calc section's heading, when *row* starts one."""
            if listed and row.section != state["section"] and row.section <= len(listed):
                state["section"] = row.section
                part = listed[row.section - 1]
                self._heading(part.label if row.source != "Table" else f"  {part.label}",
                              "A calc section: what is defined in it is not seen after the next "
                              "break, unless it is global", BAND.name())

        def put_book(name: str, entries: list) -> None:
            first = entries[0][1]
            section_of(first)
            reads = [e for e in entries if not e[1].closed]
            own = [e for e in entries if e[1].closed]
            kind = " · self-contained" if first.group_contained else ""
            page = f" · page {first.group_page}" if first.group_page else ""
            count = f" ({names(len(reads))})" if reads else ""
            tip = (f"The workbook {name}: what the equations read of it — its CalcForge variables"
                   + ("; its Excel names are for its own cells only" if first.group_contained
                      else ", and its Excel names dialled in (Sheet.Name)"))
            head = self._group(None, f"book:{name}", f"{name}{page}{kind}{count}", tip)
            for index, row in reads:
                nodes[index] = self._row_node(head, index, row)
            if own:
                inner = self._group(head, f"own:{name}", f"Its own cells only ({len(own)})",
                                    f"{name} is self-contained: its Excel names, read by its "
                                    f"own cells only, shown for reference")
                inner.setForeground(0, QBrush(QColor(CLOSED_GREY)))
                for index, row in own:
                    nodes[index] = self._row_node(inner, index, row)

        blocks = {}
        for index, row in main:
            if row.source == "Table":
                while books:
                    put_book(*books.pop(0))           # every workbook before the tables
            elif row.key is not None:
                while books and tuple(books[0][1][0][1].order or last) < tuple(row.key):
                    put_book(*books.pop(0))           # a workbook before this equation
            if row.source == "Table" and not state["tables"]:
                state["tables"] = True
                state["section"] = None
                self._heading("Tables", "What the tables give the equations: named cells, and "
                                        "Table.Column for each heading")
            section_of(row)
            parent = None
            if row.block:
                parent = blocks.get(row.block)
                if parent is None:
                    kind = " · self-contained" if row.block_contained else ""
                    tip = ("What it defines stays inside it: nothing after the block reads it"
                           if row.block_contained else "What it defines is read after it too")
                    parent = blocks[row.block] = self._group(
                        None, f"block:{row.block}",
                        f"{row.block_label} · page {row.page}{kind} "
                        f"({names(counts[row.block])})", tip)
            nodes[index] = self._row_node(parent, index, row)
        while books:
            put_book(*books.pop(0))
        if current in nodes:
            self.tree.setCurrentItem(nodes[current])
        self._filling = False
        self.empty.setVisible(not self.rows)
        self._mark_in_force()
        self._fit_columns()

    def _fit_columns(self) -> None:
        """Value as wide as its widest shown value, up to a third of the
        panel (at least 48 px); Name has the rest."""
        width = self.tree.viewport().width()
        wanted = max([self.tree.sizeHintForColumn(1), 48])
        self.tree.header().resizeSection(1, max(48, min(wanted + 8, width // 3)))

    def eventFilter(self, watched, event) -> bool:
        if watched is self.tree and event.type() == QEvent.Resize:
            self._fit_columns()
        return super().eventFilter(watched, event)

    # -- global or not (calc sections) ------------------------------------------------------
    def _menu(self, pos) -> None:
        node = self.tree.itemAt(pos)
        if node is not None:
            self.tree.setCurrentItem(node)
        menu = self.build_menu(node)
        if menu is not None:
            menu.exec(self.tree.viewport().mapToGlobal(pos))

    def build_menu(self, node=None) -> Optional[QMenu]:
        """A row's right-click menu: of *node*, or of the current row."""
        node = node if node is not None else self.tree.currentItem()
        row = self.row_of(node)
        if row is None:
            return None
        menu = QMenu(self)
        menu.setProperty("cf_context", "variables")
        menu.addAction("Go to", lambda: self.go_to(node))
        if row.source != "Measurement" and not row.closed:
            act = menu.addAction("Make Local" if row.is_global else "Make Global",
                                 lambda: self.set_global(row, not row.is_global))
            act.setToolTip("A global variable or cell is read by every later calc section")
        return menu

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
    def toggle_group(self, key: str) -> None:
        """A group's heading clicked: what is in it shown, or put away."""
        node = self.group_node(key)
        if node is not None:
            node.setExpanded(not node.isExpanded())     # (opened follows: _expanded)
            return
        if key in self.opened:
            self.opened.discard(key)
        else:
            self.opened.add(key)
        self._fill()

    def first_row(self):
        """The first variable's row, at any depth, its groups opened so it
        can be seen (and right-clicked); None when there is none."""
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        found = QTreeWidgetItemIterator(self.tree)
        while found.value() is not None:
            node = found.value()
            if self.row_of(node) is not None:
                parent = node.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                return node
            found += 1
        return None

    def group_node(self, key: str):
        """The heading of group *key* ("block:uid", "book:Name", "own:Name")."""
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        found = QTreeWidgetItemIterator(self.tree)
        while found.value() is not None:
            node = found.value()
            if node.data(0, GROUP_ROLE) == key:
                return node
            found += 1
        return None

    def _expanded(self, node, on: bool) -> None:
        if self._filling or self._finding:
            return                              # (the item may be going)
        key = node.data(0, GROUP_ROLE)
        if key:
            (self.opened.add if on else self.opened.discard)(key)

    def row_of(self, node) -> Optional[VariableRow]:
        index = node.data(0, Qt.UserRole) if node is not None else None
        return self.rows[index] if index is not None and 0 <= index < len(self.rows) else None

    def go_to(self, node) -> None:
        group = node.data(0, GROUP_ROLE) if node is not None else None
        if group:
            self.toggle_group(group)
            return
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
        # brought into view, not centred: centring an equation at the left of
        # the page put the desk beside it in the middle (F-36)
        window.view.ensureVisible(item, 60, 60)
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
