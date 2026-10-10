"""Copying cells to and from other programs.

What goes on the clipboard, as Excel puts it there:

* plain text: the cells as shown, a tab between columns, a line per row;
* HTML: a table with the cells' look (fonts, fills, borders, alignment);
* "XML Spreadsheet" (Excel's own, on Windows): values, formulas in R1C1
  form and styles, so formulas survive a paste into Excel and back;
* CalcForge's own (JSON): exactly what was typed and every style.

Pasting takes the richest of these that is there.
"""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from typing import Optional
from xml.etree import ElementTree as ET

from . import formula as F
from .numfmt import format_value
from .refs import MAX_COLS, MAX_ROWS, CellRef, col_letters
from .store import style_from_dict, style_to_dict
from .style import Border, Style
from .values import BLANK, ErrorValue, Qty

MIME_OWN = "application/x-calcforge-cells"
R1C1_MARK = "\x01"           # a formula still in R1C1 form (from Excel)
MIME_EXCEL_XML = 'application/x-qt-windows-mime;value="XML Spreadsheet"'
MIME_EXCEL_XML_ALT = "XML Spreadsheet"


# -- what is copied ----------------------------------------------------------------------
def block_data(sheet, top: int, left: int, bottom: int, right: int) -> dict:
    """The block as CalcForge's own clipboard data."""
    wb = sheet.workbook
    rows = []
    for r in range(top, bottom + 1):
        line = []
        for c in range(left, right + 1):
            cell = sheet.cells.get((r, c))
            if cell is None:
                line.append(None)
            else:
                line.append([cell.input, style_to_dict(wb.styles.get(cell.style)), cell.comment])
        rows.append(line)
    widths = [sheet.width(c) for c in range(left, right + 1)]
    heights = [sheet.height(r) for r in range(top, bottom + 1)]
    merges = [[m[0] - top, m[1] - left, m[2] - top, m[3] - left] for m in sheet.merges
              if m[0] >= top and m[2] <= bottom and m[1] >= left and m[3] <= right]
    return {"origin": [top, left], "sheet": sheet.name, "rows": rows,
            "widths": widths, "heights": heights, "merges": merges}


def shown_text(sheet, row: int, col: int) -> str:
    cell = sheet.cells.get((row, col))
    if cell is None:
        return ""
    st = sheet.workbook.styles.get(cell.style)
    return format_value(cell.value, st.number_format, st.unit).text


def as_text(sheet, top, left, bottom, right) -> str:
    lines = []
    for r in range(top, bottom + 1):
        cells = []
        for c in range(left, right + 1):
            t = shown_text(sheet, r, c)
            if any(ch in t for ch in '\t\n"'):
                t = '"' + t.replace('"', '""') + '"'
            cells.append(t)
        lines.append("\t".join(cells))
    return "\r\n".join(lines) + "\r\n"


_BORDER_CSS = {"thin": "1px solid", "hair": "1px solid", "medium": "2px solid", "thick": "3px solid",
               "dashed": "1px dashed", "dotted": "1px dotted", "double": "3px double"}


def _css(st: Style, value) -> str:
    out = []
    if st.font:
        out.append(f"font-family:{st.font}")
    if st.size:
        out.append(f"font-size:{st.size:g}pt")
    if st.bold:
        out.append("font-weight:700")
    if st.italic:
        out.append("font-style:italic")
    deco = []
    if st.underline:
        deco.append("underline")
    if st.strike:
        deco.append("line-through")
    if deco:
        out.append("text-decoration:" + " ".join(deco))
    if st.color:
        out.append(f"color:{st.color}")
    if st.fill:
        out.append(f"background:{st.fill}")
    align = st.h_align
    if align == "general":
        align = "right" if isinstance(value, (float, Qty)) and not isinstance(value, bool) else \
            "center" if isinstance(value, (bool, ErrorValue)) else "left"
    out.append(f"text-align:{align}")
    out.append("vertical-align:" + {"center": "middle"}.get(st.v_align, st.v_align))
    if st.wrap:
        out.append("white-space:normal")
    for side in ("left", "right", "top", "bottom"):
        b = getattr(st, side)
        if b is not None:
            out.append(f"border-{side}:{_BORDER_CSS.get(b.style, '1px solid')} {b.color}")
    if st.number_format and st.number_format != "General":
        out.append(f"mso-number-format:'{st.number_format}'")
    return ";".join(out)


def as_html(sheet, top, left, bottom, right) -> str:
    wb = sheet.workbook
    merged = {}
    covered = set()
    for m in sheet.merges:
        if m[0] >= top and m[2] <= bottom and m[1] >= left and m[3] <= right:
            merged[(m[0], m[1])] = (m[2] - m[0] + 1, m[3] - m[1] + 1)
            for r in range(m[0], m[2] + 1):
                for c in range(m[1], m[3] + 1):
                    if (r, c) != (m[0], m[1]):
                        covered.add((r, c))
    parts = ["<html><body><table style='border-collapse:collapse'>"]
    for c in range(left, right + 1):
        parts.append(f"<col width={round(sheet.width(c) * 96 / 72)}>")
    for r in range(top, bottom + 1):
        parts.append(f"<tr height={round(sheet.height(r) * 96 / 72)}>")
        for c in range(left, right + 1):
            if (r, c) in covered:
                continue
            cell = sheet.cells.get((r, c))
            st = wb.styles.get(cell.style if cell else 0)
            value = cell.value if cell else BLANK
            span = merged.get((r, c))
            attrs = f" rowspan={span[0]} colspan={span[1]}" if span else ""
            text = html.escape(shown_text(sheet, r, c)).replace("\n", "<br>")
            parts.append(f"<td{attrs} style=\"{_css(st, value)}\">{text}</td>")
        parts.append("</tr>")
    parts.append("</table></body></html>")
    return "".join(parts)


# -- R1C1, as Excel's XML Spreadsheet writes formulas ----------------------------------------------
def to_r1c1(text: str, row: int, col: int) -> str:
    """=A1+$B$2 in cell (row, col) -> =R[-r]C[-c]+R2C2."""
    def r1c1(ref: CellRef) -> str:
        r = f"R{ref.row + 1}" if ref.row_abs else ("R" if ref.row == row else f"R[{ref.row - row}]")
        c = f"C{ref.col + 1}" if ref.col_abs else ("C" if ref.col == col else f"C[{ref.col - col}]")
        return r + c

    tokens = F.tokenize(text)
    for t in tokens:
        if t.kind != "ref":
            continue
        ref = t.ref
        sheet = (F.quote_sheet(ref.sheet) + "!") if ref.sheet else ""
        if isinstance(ref, CellRef):
            t.text = sheet + r1c1(ref)
        elif ref.whole == "cols":
            a = f"C{ref.first.col + 1}" if ref.first.col_abs else f"C[{ref.first.col - col}]"
            b = f"C{ref.last.col + 1}" if ref.last.col_abs else f"C[{ref.last.col - col}]"
            t.text = sheet + (a if a == b else a + ":" + b)
        elif ref.whole == "rows":
            a = f"R{ref.first.row + 1}" if ref.first.row_abs else f"R[{ref.first.row - row}]"
            b = f"R{ref.last.row + 1}" if ref.last.row_abs else f"R[{ref.last.row - row}]"
            t.text = sheet + (a if a == b else a + ":" + b)
        else:
            t.text = sheet + r1c1(ref.first) + ":" + r1c1(ref.last)
    return F.join(tokens)


_R1C1 = re.compile(r"""(?P<sheet>(?:'(?:[^']|'')+'|[A-Za-z_][\w.]*)!)?
    (?:R(?:\[(?P<dr>-?\d+)\]|(?P<ar>\d+))?C(?:\[(?P<dc>-?\d+)\]|(?P<ac>\d+))?
       (?::R(?:\[(?P<dr2>-?\d+)\]|(?P<ar2>\d+))?C(?:\[(?P<dc2>-?\d+)\]|(?P<ac2>\d+))?)?
     |C(?:\[(?P<wc>-?\d+)\]|(?P<awc>\d+))(?::C(?:\[(?P<wc2>-?\d+)\]|(?P<awc2>\d+)))?
     |R(?:\[(?P<wr>-?\d+)\]|(?P<awr>\d+))(?::R(?:\[(?P<wr2>-?\d+)\]|(?P<awr2>\d+)))?)
    (?![\w(])""", re.X)


def from_r1c1(text: str, row: int, col: int) -> str:
    """=R[-1]C+R2C2 in cell (row, col) -> =A1+$B$2 (text outside strings only)."""
    out = []
    parts = re.split(r'("(?:[^"]|"")*")', text)
    for k, part in enumerate(parts):
        if k % 2:
            out.append(part)
            continue
        out.append(_R1C1.sub(lambda m: _a1_of(m, row, col), part))
    return "".join(out)


def _a1_of(m, row, col) -> str:
    sheet = m.group("sheet") or ""

    def cell(dr, ar, dc, ac):
        r_abs, c_abs = ar is not None, ac is not None
        r = int(ar) - 1 if r_abs else row + int(dr or 0)
        c = int(ac) - 1 if c_abs else col + int(dc or 0)
        if not (0 <= r < MAX_ROWS and 0 <= c < MAX_COLS):
            return "#REF!"
        return ("$" if c_abs else "") + col_letters(c) + ("$" if r_abs else "") + str(r + 1)

    if m.group("wc") is not None or m.group("awc") is not None:
        def c_of(d, a):
            return ("$" + col_letters(int(a) - 1)) if a is not None else col_letters(col + int(d or 0))
        a = c_of(m.group("wc"), m.group("awc"))
        b = c_of(m.group("wc2"), m.group("awc2")) if (m.group("wc2") or m.group("awc2")) else a
        return sheet + a + ":" + b
    if m.group("wr") is not None or m.group("awr") is not None:
        def r_of(d, a):
            return ("$" + a) if a is not None else str(row + int(d or 0) + 1)
        a = r_of(m.group("wr"), m.group("awr"))
        b = r_of(m.group("wr2"), m.group("awr2")) if (m.group("wr2") or m.group("awr2")) else a
        return sheet + a + ":" + b
    first = cell(m.group("dr"), m.group("ar"), m.group("dc"), m.group("ac"))
    whole = m.group(0)
    if ":" in whole[len(sheet):]:
        second = cell(m.group("dr2"), m.group("ar2"), m.group("dc2"), m.group("ac2"))
        return sheet + first + ":" + second
    return sheet + first


# -- Excel's XML Spreadsheet ------------------------------------------------------------------
_SS = "urn:schemas-microsoft-com:office:spreadsheet"


def as_excel_xml(sheet, top, left, bottom, right) -> bytes:
    wb = sheet.workbook
    styles = {}
    rows_xml = []
    merged = {(m[0], m[1]): m for m in sheet.merges
              if m[0] >= top and m[2] <= bottom and m[1] >= left and m[3] <= right}
    covered = {(r, c) for m in merged.values() for r in range(m[0], m[2] + 1)
               for c in range(m[1], m[3] + 1) if (r, c) != (m[0], m[1])}
    for r in range(top, bottom + 1):
        cells_xml = []
        expected = left
        for c in range(left, right + 1):
            if (r, c) in covered:
                continue
            cell = sheet.cells.get((r, c))
            if cell is None and (r, c) not in merged:
                continue
            attrs = []
            if c != expected:
                attrs.append(f'ss:Index="{c - left + 1}"')
            st = wb.styles.get(cell.style if cell else 0)
            sid = styles.setdefault(st, f"s{len(styles) + 20}")
            attrs.append(f'ss:StyleID="{sid}"')
            m = merged.get((r, c))
            if m:
                if m[3] > m[1]:
                    attrs.append(f'ss:MergeAcross="{m[3] - m[1]}"')
                if m[2] > m[0]:
                    attrs.append(f'ss:MergeDown="{m[2] - m[0]}"')
            data = ""
            if cell is not None:
                if cell.is_formula:
                    attrs.append('ss:Formula="=' + html.escape(to_r1c1(cell.input[1:], r, c), True) + '"')
                kind, text = _xml_value(cell.value)
                if kind:
                    data = f'<Data ss:Type="{kind}">{html.escape(text)}</Data>'
            cells_xml.append(f"<Cell {' '.join(attrs)}>{data}</Cell>")
            expected = c + 1 + (m[3] - m[1] if m else 0)
        height = sheet.height(r)
        rows_xml.append(f'<Row ss:Index="{r - top + 1}" ss:Height="{height:g}">' + "".join(cells_xml) + "</Row>")
    cols_xml = "".join(f'<Column ss:Index="{c - left + 1}" ss:Width="{sheet.width(c):g}"/>'
                       for c in range(left, right + 1))
    style_xml = "".join(_xml_style(st, sid) for st, sid in styles.items())
    doc = ('<?xml version="1.0"?><?mso-application progid="Excel.Sheet"?>'
           f'<Workbook xmlns="{_SS}" xmlns:ss="{_SS}" xmlns:o="urn:schemas-microsoft-com:office:office" '
           'xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns:html="http://www.w3.org/TR/REC-html40">'
           f"<Styles>{style_xml}</Styles>"
           f'<Worksheet ss:Name="{html.escape(sheet.name)}"><Table>{cols_xml}{"".join(rows_xml)}</Table></Worksheet>'
           "</Workbook>")
    return doc.encode("utf-8")


def _xml_value(value):
    if value is BLANK or value is None:
        return None, ""
    if isinstance(value, bool):
        return "Boolean", "1" if value else "0"
    if isinstance(value, float):
        return "Number", repr(value)
    if isinstance(value, Qty):
        return "Number", repr(value.shown())
    if isinstance(value, ErrorValue):
        return "Error", value.code
    return "String", str(value)


_XML_BORDER = {"thin": ("Continuous", 1), "hair": ("Continuous", 0), "medium": ("Continuous", 2),
               "thick": ("Continuous", 3), "dashed": ("Dash", 1), "dotted": ("Dot", 1), "double": ("Double", 3)}


def _xml_style(st: Style, sid: str) -> str:
    out = [f'<Style ss:ID="{sid}">']
    h = {"general": None, "left": "Left", "center": "Center", "right": "Right", "fill": "Fill",
         "justify": "Justify", "centerAcross": "CenterAcrossSelection"}.get(st.h_align)
    v = {"top": "Top", "center": "Center", "bottom": "Bottom"}.get(st.v_align, "Bottom")
    attrs = [f'ss:Vertical="{v}"']
    if h:
        attrs.append(f'ss:Horizontal="{h}"')
    if st.wrap:
        attrs.append('ss:WrapText="1"')
    if st.indent:
        attrs.append(f'ss:Indent="{st.indent}"')
    if st.rotation:
        attrs.append(f'ss:Rotate="{st.rotation}"')
    out.append(f"<Alignment {' '.join(attrs)}/>")
    borders = []
    for side, name in (("left", "Left"), ("right", "Right"), ("top", "Top"), ("bottom", "Bottom")):
        b = getattr(st, side)
        if b is not None:
            line, weight = _XML_BORDER.get(b.style, ("Continuous", 1))
            borders.append(f'<Border ss:Position="{name}" ss:LineStyle="{line}" ss:Weight="{weight}" '
                           f'ss:Color="{b.color}"/>')
    if borders:
        out.append("<Borders>" + "".join(borders) + "</Borders>")
    font = []
    if st.font:
        font.append(f'ss:FontName="{html.escape(st.font)}"')
    if st.size:
        font.append(f'ss:Size="{st.size:g}"')
    if st.bold:
        font.append('ss:Bold="1"')
    if st.italic:
        font.append('ss:Italic="1"')
    if st.underline:
        font.append(f'ss:Underline="{"Double" if st.underline == "double" else "Single"}"')
    if st.strike:
        font.append('ss:StrikeThrough="1"')
    if st.color:
        font.append(f'ss:Color="{st.color}"')
    if font:
        out.append(f"<Font {' '.join(font)}/>")
    if st.fill:
        out.append(f'<Interior ss:Color="{st.fill}" ss:Pattern="Solid"/>')
    if st.number_format:
        out.append(f'<NumberFormat ss:Format="{html.escape(st.number_format, True)}"/>')
    out.append("</Style>")
    return "".join(out)


def _ns(tag: str) -> str:
    return f"{{{_SS}}}{tag}"


def from_excel_xml(data: bytes) -> Optional[dict]:
    """Excel's XML Spreadsheet as CalcForge's own clipboard data (formulas
    turned back into A1 form for the cell they land in)."""
    try:
        root = ET.fromstring(data.rstrip(b"\x00"))
    except ET.ParseError:
        return None
    styles = {}
    for st in root.iter(_ns("Style")):
        styles[st.get(_ns("ID"))] = style_to_dict(_style_of_xml(st))
    table = next(root.iter(_ns("Table")), None)
    if table is None:
        return None
    grid: dict = {}
    widths: dict = {}
    heights: dict = {}
    merges = []
    col_i = 0
    for column in table.findall(_ns("Column")):
        idx = column.get(_ns("Index"))
        col_i = int(idx) - 1 if idx else col_i
        span = int(column.get(_ns("Span"), "0"))
        width = column.get(_ns("Width"))
        for k in range(span + 1):
            if width:
                widths[col_i + k] = float(width)
        col_i += span + 1
    row_i = 0
    for row in table.findall(_ns("Row")):
        idx = row.get(_ns("Index"))
        row_i = int(idx) - 1 if idx else row_i
        if row.get(_ns("Height")):
            heights[row_i] = float(row.get(_ns("Height")))
        c = 0
        for cell in row.findall(_ns("Cell")):
            idx = cell.get(_ns("Index"))
            c = int(idx) - 1 if idx else c
            style = styles.get(cell.get(_ns("StyleID")), {})
            formula = cell.get(_ns("Formula"))
            data_el = cell.find(_ns("Data"))
            text = ""
            if formula:
                text = R1C1_MARK + formula      # turned into A1 where it lands
            elif data_el is not None:
                kind = data_el.get(_ns("Type"))
                raw = "".join(data_el.itertext())
                if kind == "Number":
                    x = float(raw)
                    text = repr(x) if x != int(x) else str(int(x))
                    fmt = style.get("number_format", "")
                    if fmt and _looks_date(fmt):
                        text = raw
                elif kind == "Boolean":
                    text = "TRUE" if raw.strip() in ("1", "true") else "FALSE"
                elif kind == "Error":
                    text = raw
                elif kind == "DateTime":
                    from datetime import datetime
                    from .dates import serial_from_datetime
                    try:
                        text = repr(serial_from_datetime(datetime.fromisoformat(raw[:19])))
                    except ValueError:
                        text = raw
                else:
                    from .inputs import read_value
                    got, _ = read_value(raw)
                    text = raw if isinstance(got, str) and got == raw else "'" + raw
            comment = None
            com = cell.find(_ns("Comment"))
            if com is not None:
                comment = "".join(com.itertext()).strip()
            grid[(row_i, c)] = [text, style, comment]
            across = int(cell.get(_ns("MergeAcross"), "0"))
            down = int(cell.get(_ns("MergeDown"), "0"))
            if across or down:
                merges.append([row_i, c, row_i + down, c + across])
            c += 1 + across
        row_i += 1
    if not grid:
        return None
    h = max(r for r, _ in grid) + 1
    w = max(c for _, c in grid) + 1
    rows = [[grid.get((r, c)) for c in range(w)] for r in range(h)]
    return {"origin": [0, 0], "sheet": None, "rows": rows,
            "widths": [widths.get(c) for c in range(w)], "heights": [heights.get(r) for r in range(h)],
            "merges": merges}


def _looks_date(fmt: str) -> bool:
    from .numfmt import is_date_format
    return is_date_format(fmt)


def _style_of_xml(el) -> Style:
    kw = {}
    al = el.find(_ns("Alignment"))
    if al is not None:
        h = al.get(_ns("Horizontal"))
        if h:
            kw["h_align"] = {"Left": "left", "Center": "center", "Right": "right", "Fill": "fill",
                             "Justify": "justify", "CenterAcrossSelection": "centerAcross"}.get(h, "general")
        v = al.get(_ns("Vertical"))
        if v:
            kw["v_align"] = {"Top": "top", "Center": "center", "Bottom": "bottom"}.get(v, "bottom")
        if al.get(_ns("WrapText")) == "1":
            kw["wrap"] = True
    for b in el.iter(_ns("Border")):
        side = (b.get(_ns("Position")) or "").lower()
        if side in ("left", "right", "top", "bottom"):
            weight = int(b.get(_ns("Weight"), "1"))
            line = b.get(_ns("LineStyle"), "Continuous")
            style = {"Dash": "dashed", "Dot": "dotted", "Double": "double"}.get(
                line, {0: "hair", 1: "thin", 2: "medium", 3: "thick"}.get(weight, "thin"))
            kw[side] = Border(style, b.get(_ns("Color")) or "#000000")
    font = el.find(_ns("Font"))
    if font is not None:
        if font.get(_ns("FontName")):
            kw["font"] = font.get(_ns("FontName"))
        if font.get(_ns("Size")):
            kw["size"] = float(font.get(_ns("Size")))
        if font.get(_ns("Bold")) == "1":
            kw["bold"] = True
        if font.get(_ns("Italic")) == "1":
            kw["italic"] = True
        if font.get(_ns("Underline")):
            kw["underline"] = "double" if font.get(_ns("Underline")) == "Double" else "single"
        if font.get(_ns("StrikeThrough")) == "1":
            kw["strike"] = True
        if font.get(_ns("Color")) and font.get(_ns("Color")).lower() != "#000000":
            kw["color"] = font.get(_ns("Color"))
    interior = el.find(_ns("Interior"))
    if interior is not None and interior.get(_ns("Color")) and interior.get(_ns("Pattern"), "Solid") != "None":
        kw["fill"] = interior.get(_ns("Color"))
    nf = el.find(_ns("NumberFormat"))
    if nf is not None and nf.get(_ns("Format")) and nf.get(_ns("Format")) != "General":
        fmt = nf.get(_ns("Format"))
        kw["number_format"] = {"Short Date": "d/mm/yyyy", "Percent": "0.00%", "Fixed": "0.00",
                               "Standard": "#,##0.00", "Scientific": "0.00E+00",
                               "Short Time": "h:mm", "Long Time": "h:mm:ss"}.get(fmt, fmt)
    return Style(**kw)


# -- plain text and HTML in ---------------------------------------------------------------------
def from_text(text: str) -> dict:
    """Tab-separated text (Excel's plain text, or any copied table)."""
    rows = []
    for line in _split_rows(text):
        rows.append([[cell, {}, None] if cell != "" else None for cell in line])
    w = max((len(r) for r in rows), default=0)
    rows = [r + [None] * (w - len(r)) for r in rows]
    return {"origin": [0, 0], "sheet": None, "rows": rows, "widths": [], "heights": [], "merges": [],
            "plain": True}


def _split_rows(text: str) -> list:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    rows, row, cell, i, quoted = [], [], [], 0, False
    while i < len(text):
        ch = text[i]
        if quoted:
            if ch == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    cell.append('"')
                    i += 2
                    continue
                quoted = False
            else:
                cell.append(ch)
        elif ch == '"' and not cell:
            quoted = True
        elif ch == "\t":
            row.append("".join(cell))
            cell = []
        elif ch == "\n":
            row.append("".join(cell))
            rows.append(row)
            row, cell = [], []
        else:
            cell.append(ch)
        i += 1
    row.append("".join(cell))
    rows.append(row)
    return rows


class _TableReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None
        self.style = ""
        self.spans = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
            self.style = a.get("style", "") + (";font-weight:700" if tag == "th" else "")
            self.spans.append((len(self.rows), len(self.row), int(a.get("rowspan", 1) or 1),
                               int(a.get("colspan", 1) or 1)))
        elif tag == "br" and self.cell is not None:
            self.cell.append("\n")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(("".join(self.cell).strip(), self.style))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def from_html(text: str) -> Optional[dict]:
    reader = _TableReader()
    try:
        reader.feed(text)
    except Exception:
        return None
    if not reader.rows:
        return None
    rows = []
    for r in reader.rows:
        rows.append([[t, style_to_dict(_style_of_css(css)), None] if t or css else None for t, css in r])
    w = max(len(r) for r in rows)
    rows = [r + [None] * (w - len(r)) for r in rows]
    return {"origin": [0, 0], "sheet": None, "rows": rows, "widths": [], "heights": [], "merges": [],
            "plain": True}


def _style_of_css(css: str) -> Style:
    kw = {}
    for part in css.split(";"):
        if ":" not in part:
            continue
        k, v = (x.strip().lower() for x in part.split(":", 1))
        if k == "font-weight" and (v in ("bold", "bolder") or v.isdigit() and int(v) >= 600):
            kw["bold"] = True
        elif k == "font-style" and v == "italic":
            kw["italic"] = True
        elif k in ("background", "background-color") and v.startswith("#"):
            kw["fill"] = v
        elif k == "color" and v.startswith("#") and v not in ("#000", "#000000"):
            kw["color"] = v
        elif k == "text-align" and v in ("left", "center", "right"):
            kw["h_align"] = v
    return Style(**kw)


def from_clipboard(formats: dict) -> Optional[dict]:
    """The richest data among what the clipboard has: formats maps a MIME
    type to its bytes."""
    own = formats.get(MIME_OWN)
    if own:
        try:
            return json.loads(own.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            pass
    for key in (MIME_EXCEL_XML, MIME_EXCEL_XML_ALT):
        if formats.get(key):
            got = from_excel_xml(formats[key])
            if got:
                return got
    if formats.get("text/html"):
        got = from_html(formats["text/html"].decode("utf-8", "replace"))
        if got:
            return got
    if formats.get("text/plain") is not None:
        return from_text(formats["text/plain"].decode("utf-8", "replace"))
    return None


def paste(wb, sheet, row: int, col: int, data: dict, what: str = "all") -> tuple:
    """Put clipboard data at (row, col). Formulas copied from a sheet move
    by where they land, as in Excel. Returns the block filled."""
    rows = data["rows"]
    top0, left0 = data.get("origin", [0, 0])
    drow, dcol = row - top0, col - left0
    h = len(rows)
    w = max((len(r) for r in rows), default=0)
    with wb.transaction("Paste"):
        for i, line in enumerate(rows):
            for j in range(w):
                got = line[j] if j < len(line) else None
                r, c = row + i, col + j
                target = sheet.cells.get((r, c))
                old = target.state() if target else ("", 0, None)
                if got is None:
                    if what == "all":
                        wb._set_state(sheet, r, c, ("", 0, None))
                    continue
                text, style_dict, comment = got[0], got[1], got[2] if len(got) > 2 else None
                if text.startswith(R1C1_MARK):
                    text = from_r1c1(text[1:], r, c)
                elif text.startswith("=") and len(text) > 1:
                    # as in Excel, a copied formula reads the sheet it lands on
                    text = "=" + F.moved_formula(text[1:], drow, dcol)
                style = wb.styles.add(style_from_dict(style_dict)) if style_dict else 0
                if data.get("plain") and not style_dict:
                    style = old[1]
                if what == "values":
                    wb._set_state(sheet, r, c, (_value_text(wb, text, sheet, r, c), old[1], old[2]))
                elif what == "formulas":
                    wb._set_state(sheet, r, c, (text, old[1], old[2]))
                elif what == "formats":
                    wb._set_state(sheet, r, c, (old[0], style, old[2]))
                else:
                    if data.get("plain") and not text.startswith("="):
                        from .inputs import read_value
                        _v, fmt = read_value(text, wb.day_first)
                        if fmt and wb.styles.get(style).number_format in (None, "General"):
                            from dataclasses import replace
                            style = wb.styles.add(replace(wb.styles.get(style), number_format=fmt))
                    wb._set_state(sheet, r, c, (text, style, comment))
        if what in ("all", "formats"):
            for m in data.get("merges", []):
                t, l, b, rr = m
                wb.merge(sheet, row + t, col + l, row + b, col + rr)
    return row, col, row + h - 1, col + w - 1


def _value_text(wb, text, sheet, r, c) -> str:
    """Paste Values: a formula's value as typed text."""
    if not (text.startswith("=") and len(text) > 1):
        return text
    from .evaluate import evaluate_cell
    try:
        parsed = F.parse(text[1:], r, c)
    except F.FormulaError:
        return text
    value, _reads = evaluate_cell(wb, sheet, r, c, parsed.tree)
    from .workbook import value_as_input
    return value_as_input(value)


def to_clipboard(sheet, top, left, bottom, right) -> dict:
    """MIME type -> bytes for a copy."""
    return {
        MIME_OWN: json.dumps(block_data(sheet, top, left, bottom, right)).encode("utf-8"),
        MIME_EXCEL_XML: as_excel_xml(sheet, top, left, bottom, right),
        "text/html": as_html(sheet, top, left, bottom, right).encode("utf-8"),
        "text/plain": as_text(sheet, top, left, bottom, right).encode("utf-8"),
    }
