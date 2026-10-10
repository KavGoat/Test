"""The table's controls on the properties toolbar (Excel's Home tab, compact).

While a table is open the toolbar shows these instead of the pen controls
(the bar itself stays, so the page never jumps): font, size, bold, italic,
underline, text and fill colour, alignment, wrap, merge, borders, number
format with fewer/more decimals and a display unit, rows and columns,
Format Painter and Format Cells.
"""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QComboBox, QFontComboBox, QLabel, QLineEdit, QMenu, QToolButton)

from ..sheet.numfmt import is_date_format
from ..sheet.values import UnitTextError, unit_parts
from .widgets import ColorButton

NUMBER_FORMATS = [("General", None), ("Number", "0.00"), ("Currency", "$#,##0.00"),
                  ("Percent", "0%"), ("Scientific", "0.00E+00"), ("Fraction", "# ?/?"),
                  ("Date", "d/mm/yyyy"), ("Time", "h:mm"), ("Text", "@")]


class TableControls:
    def __init__(self, window):
        self.window = window
        self.actions: list = []
        self._syncing = False
        bar = window.style_bar
        add = lambda w: self.actions.append(bar.addWidget(w))

        self.font = QFontComboBox()
        self.font.setMaximumWidth(150)
        self.font.setToolTip("Font")
        self.font.currentFontChanged.connect(lambda f: self._set(font=f.family() if f.family() != "Calibri" else None))
        add(self.font)
        self.size = QComboBox()
        self.size.setEditable(True)
        self.size.addItems(["8", "9", "10", "11", "12", "14", "16", "18", "20", "24", "28", "36"])
        self.size.setFixedWidth(52)
        self.size.setToolTip("Font size")
        self.size.lineEdit().editingFinished.connect(self._size_chosen)
        self.size.activated.connect(lambda _i: self._size_chosen())
        add(self.size)
        self.buttons = {}
        for key, text, tip in (("bold", "B", "Bold (Ctrl+B)"), ("italic", "I", "Italic (Ctrl+I)"),
                               ("underline", "U", "Underline (Ctrl+U)")):
            b = QToolButton()
            b.setText(text)
            f = b.font()
            f.setBold(key == "bold")
            f.setItalic(key == "italic")
            f.setUnderline(key == "underline")
            b.setFont(f)
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, k=key: self._toggle(k))
            self.buttons[key] = b
            add(b)
        self.text_colour = ColorButton("#000000", True, "Font colour")
        self.text_colour.colorChanged.connect(lambda c: self._set(color=c or None))
        add(self.text_colour)
        self.fill = ColorButton("", True, "Fill colour")
        self.fill.colorChanged.connect(lambda c: self._set(fill=c or None))
        add(self.fill)
        add(self._sep())
        self.align = {}
        for key, text, tip in (("left", "⯇", "Align left"), ("center", "≡", "Center"),
                               ("right", "⯈", "Align right")):
            b = QToolButton()
            b.setText(text)
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, k=key: self._align(k))
            self.align[key] = b
            add(b)
        self.valign = QComboBox()
        self.valign.addItems(["Bottom", "Middle", "Top"])
        self.valign.setToolTip("Vertical alignment")
        self.valign.activated.connect(lambda i: self._set(v_align=["bottom", "center", "top"][i]))
        add(self.valign)
        self.wrap = QToolButton()
        self.wrap.setText("Wrap")
        self.wrap.setCheckable(True)
        self.wrap.setAutoRaise(True)
        self.wrap.setToolTip("Wrap text onto more lines in the cell")
        self.wrap.clicked.connect(lambda c: self._set(wrap=c))
        add(self.wrap)
        merge = QToolButton()
        merge.setText("Merge")
        merge.setPopupMode(QToolButton.InstantPopup)
        merge.setAutoRaise(True)
        menu = QMenu(merge)
        for label, how in (("Merge && Center", "center"), ("Merge Across", "across"),
                           ("Merge Cells", "cells"), ("Unmerge Cells", "unmerge")):
            menu.addAction(label, lambda h=how: self._tables().merge(h))
        merge.setMenu(menu)
        add(merge)
        borders = QToolButton()
        borders.setText("Borders")
        borders.setPopupMode(QToolButton.InstantPopup)
        borders.setAutoRaise(True)
        menu = QMenu(borders)
        for label, which in (("All Borders", "all"), ("Outside Borders", "outside"),
                             ("Inside Borders", "inside"), ("Thick Box Border", "thick_box"),
                             ("Top Border", "top"), ("Bottom Border", "bottom"), ("Left Border", "left"),
                             ("Right Border", "right"), ("No Border", "none")):
            menu.addAction(label, lambda w=which: self._tables().borders(w))
        borders.setMenu(menu)
        add(borders)
        add(self._sep())
        self.number = QComboBox()
        for label, _code in NUMBER_FORMATS:
            self.number.addItem(label)
        self.number.addItem("More…")
        self.number.setToolTip("Number format")
        self.number.activated.connect(self._number_chosen)
        add(self.number)
        for text, step, tip in (("←.0", -1, "Fewer decimal places"), (".00→", 1, "More decimal places")):
            b = QToolButton()
            b.setText(text)
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, s=step: self._decimals(s))
            add(b)
        self.unit = QLineEdit()
        self.unit.setPlaceholderText("unit")
        self.unit.setFixedWidth(64)
        self.unit.setToolTip("Show quantities in this unit (kN, kN/m, MPa…); blank: as typed")
        self.unit.editingFinished.connect(self._unit_chosen)
        add(self.unit)
        add(self._sep())
        cells = QToolButton()
        cells.setText("Rows && Columns")
        cells.setPopupMode(QToolButton.InstantPopup)
        cells.setAutoRaise(True)
        menu = QMenu(cells)
        t = self._tables
        menu.addAction("Insert Rows Above", lambda: t().insert_rows())
        menu.addAction("Insert Rows Below", lambda: t().insert_rows(below=True))
        menu.addAction("Insert Columns Left", lambda: t().insert_cols())
        menu.addAction("Insert Columns Right", lambda: t().insert_cols(right=True))
        menu.addSeparator()
        menu.addAction("Delete Rows", lambda: t().delete_rows())
        menu.addAction("Delete Columns", lambda: t().delete_cols())
        menu.addSeparator()
        menu.addAction("Distribute Rows Evenly", lambda: t().distribute("row"))
        menu.addAction("Distribute Columns Evenly", lambda: t().distribute("col"))
        menu.addAction("AutoFit Column Width", lambda: t().autofit(
            "col", list(range(t().selection()[1], t().selection()[3] + 1))))
        menu.addAction("AutoFit Row Height", lambda: t().autofit(
            "row", list(range(t().selection()[0], t().selection()[2] + 1))))
        cells.setMenu(menu)
        add(cells)
        self.painter = QToolButton()
        self.painter.setText("Format Painter")
        self.painter.setCheckable(True)
        self.painter.setAutoRaise(True)
        self.painter.setToolTip("Copy the selected cells' look, then click (or drag over) "
                                "the cells to give it to")
        self.painter.clicked.connect(self._painter)
        add(self.painter)
        fmt = QToolButton()
        fmt.setText("Format…")
        fmt.setAutoRaise(True)
        fmt.setToolTip("Format Cells (Ctrl+1)")
        fmt.clicked.connect(window.format_cells_dialog)
        add(fmt)
        for action in self.actions:
            action.setVisible(False)

    @staticmethod
    def _sep():
        label = QLabel(" ")
        return label

    def _tables(self):
        return self.window.view.tables

    # -- applying -------------------------------------------------------------------------
    def _set(self, **fields) -> None:
        if self._syncing or not self._tables().is_open():
            return
        self._tables().format(**fields)
        self.window.view.setFocus()

    def _toggle(self, key: str) -> None:
        if self._syncing or not self._tables().is_open():
            return
        self._tables().toggle(key)
        self.window.view.setFocus()

    def _align(self, key: str) -> None:
        st = self._style()
        self._set(h_align="general" if st is not None and st.h_align == key else key)

    def _size_chosen(self) -> None:
        try:
            size = float(self.size.currentText())
        except ValueError:
            return
        self._set(size=None if size == 11.0 else size)

    def _number_chosen(self, index: int) -> None:
        if index >= len(NUMBER_FORMATS):
            self.window.format_cells_dialog()
            return
        self._set(number_format=NUMBER_FORMATS[index][1])

    def _decimals(self, step: int) -> None:
        st = self._style()
        if st is None:
            return
        from ..sheet.values import is_number
        code = st.number_format or "General"
        if code == "General":
            tables = self._tables()
            value = tables.item.sheet.value(*tables.active)
            text = ""
            if is_number(value):
                from ..sheet.values import Qty, general_number
                text = general_number(value.shown() if isinstance(value, Qty) else value)
            places = len(text.partition(".")[2]) if "." in text else 0
            code = "0" + ("." + "0" * places if places else "")
        new = _with_decimals(code, step)
        if new is not None:
            self._set(number_format=new)

    def _unit_chosen(self) -> None:
        if self._syncing:
            return
        text = self.unit.text().strip()
        if text:
            try:
                unit_parts(text)
            except UnitTextError:
                self.window.view.statusMessage.emit(f"“{text}” is not a unit")
                return
        st = self._style()
        if st is not None and (st.unit or "") != text:
            self._set(unit=text or None)

    def _painter(self, on: bool) -> None:
        tables = self._tables()
        if not tables.is_open():
            self.painter.setChecked(False)
            return
        if on:
            item = tables.item
            t, l, b, r = tables.selection()
            wb = item.sheet.workbook
            tables.held_format = [[wb.style_of(item.sheet, i, j) for j in range(l, r + 1)]
                                  for i in range(t, b + 1)]
            self.window.view.statusMessage.emit("Format Painter: click or drag over the cells to give the look to")
        else:
            tables.held_format = None

    # -- showing ---------------------------------------------------------------------------
    def _style(self):
        tables = self._tables()
        if not tables.is_open():
            return None
        item = tables.item
        return item.sheet.workbook.style_of(item.sheet, *tables.active)

    def show(self, on: bool) -> None:
        for action in self.actions:
            action.setVisible(on)

    def sync(self) -> None:
        """Show the active cell's look."""
        st = self._style()
        if st is None:
            return
        self._syncing = True
        try:
            self.font.setCurrentFont(QFont(st.font or "Calibri"))
            self.size.setCurrentText(f"{st.size or 11:g}")
            self.buttons["bold"].setChecked(st.bold)
            self.buttons["italic"].setChecked(st.italic)
            self.buttons["underline"].setChecked(bool(st.underline))
            for key, b in self.align.items():
                b.setChecked(st.h_align == key)
            self.valign.setCurrentIndex({"bottom": 0, "center": 1, "top": 2}.get(st.v_align, 0))
            self.wrap.setChecked(st.wrap)
            code = st.number_format
            index = 0
            for i, (_label, c) in enumerate(NUMBER_FORMATS):
                if c == code:
                    index = i
                    break
            else:
                if code and "%" in code:
                    index = 3
                elif code and is_date_format(code):
                    index = 6
                elif code:
                    index = 1
            self.number.setCurrentIndex(index)
            self.unit.setText(st.unit or "")
        finally:
            self._syncing = False


def _with_decimals(code: str, step: int):
    """The format with one decimal place more or fewer: 0.00 -> 0.000 / 0.0,
    #,##0 -> #,##0.0, 0.0% -> 0.00%, in every section."""
    out = []
    for sec in code.split(";"):
        out.append(_section_decimals(sec, step))
    new = ";".join(out)
    return new if new != code else None


def _section_decimals(sec: str, step: int) -> str:
    # where the number's digits are, outside quoted text and [colours]
    plain = []
    quoted = bracket = False
    for i, ch in enumerate(sec):
        if ch == '"':
            quoted = not quoted
        elif ch == "[" and not quoted:
            bracket = True
        elif ch == "]" and not quoted:
            bracket = False
        elif not quoted and not bracket:
            plain.append(i)
    digits = [i for i in plain if sec[i] in "0#?"]
    if not digits:
        return sec
    exp = next((i for i in plain if sec[i] in "Ee" and i + 1 < len(sec) and sec[i + 1] in "+-"), None)
    mantissa = [i for i in digits if exp is None or i < exp]
    point = next((i for i in plain if sec[i] == "." and (exp is None or i < exp)), None)
    if point is not None:
        after = [i for i in mantissa if i > point]
        places = len(after)
        if step > 0:
            insert_at = (after[-1] + 1) if after else point + 1
            return sec[:insert_at] + "0" + sec[insert_at:]
        if places == 0:
            return sec
        if places == 1:
            return sec[:point] + sec[after[-1] + 1:]
        return sec[:after[-1]] + sec[after[-1] + 1:]
    if step < 0:
        return sec
    last = mantissa[-1]
    return sec[:last + 1] + ".0" + sec[last + 1:]
