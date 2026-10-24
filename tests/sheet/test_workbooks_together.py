"""Several Excel workbooks in one document, and what could clash between
them (the user, 2026-10-24: "think of some other issue along these lines
for merging multiple workbooks in one file ... think through all
possibilities and how they might clash"; docs/SPREADSHEET_DESIGN.md,
"Workbooks side by side").

* A formula reading another workbook ([1]Snow.xlsx's Sheet1!B2) reads it
  live when that workbook is in the document already — by its sheets as
  they are named here — and keeps Excel's last value when it isn't.
* A workbook's sheet renamed coming in ("Loads" is "Loads (2)") is still
  "Loads" to text its formulas build: INDIRECT("Loads!A1") reads its own.
* A workbook kept in the 1904 date system comes in with the same dates.
* Cells copied from one workbook to another bring the names their formulas
  use, as Excel's copy does; the destination's own name of the same
  spelling wins.
"""
from __future__ import annotations

import datetime
import zipfile

import pytest

openpyxl = pytest.importorskip("openpyxl")

from openpyxl.workbook.defined_name import DefinedName  # noqa: E402

from calcforge.sheet import clip  # noqa: E402
from calcforge.sheet.store import load_sheet  # noqa: E402
from calcforge.sheet.workbook import Workbook  # noqa: E402
from calcforge.sheet.xlsx import linked_formula, make_book, read_workbook, workbook_ident  # noqa: E402,E501


def snow(path) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["B2"] = 0.85
    ws["B3"] = "=B2*2"
    wb.defined_names["Sk"] = DefinedName("Sk", attr_text="Sheet1!$B$2")
    wb.save(path)
    return path


def linking(path, target_file="Snow.xlsx") -> str:
    """A workbook whose Sheet1!A1 reads [1]Sheet1!B2 of *target_file*, A2
    its name Sk, A3 a sheet it hasn't: Excel's last values 0.85, 0.85, 7."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = "=[1]Sheet1!B2*10"
    ws["A2"] = "=[1]!Sk"
    ws["A3"] = "='[1]Other Sheet'!C9"
    ws["A4"] = '="[1]Sheet1!B2 is text"'
    wb.save(path)
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    book = parts["xl/workbook.xml"].decode()
    book = book.replace("</sheets>", '</sheets><externalReferences><externalReference '
                        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
                        'relationships" r:id="rIdX"/></externalReferences>')
    parts["xl/workbook.xml"] = book.encode()
    rels = parts["xl/_rels/workbook.xml.rels"].decode().replace(
        "</Relationships>",
        '<Relationship Id="rIdX" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/externalLink" Target="externalLinks/externalLink1.xml"/></Relationships>')
    parts["xl/_rels/workbook.xml.rels"] = rels.encode()
    parts["xl/externalLinks/externalLink1.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<externalLink xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<externalBook r:id="rId1"><sheetNames><sheetName val="Sheet1"/></sheetNames>'
        '</externalBook></externalLink>').encode()
    parts["xl/externalLinks/_rels/externalLink1.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        f'relationships/externalLinkPath" Target="file:///C:\\Jobs\\{target_file}" '
        'TargetMode="External"/></Relationships>').encode()
    types = parts["[Content_Types].xml"].decode().replace(
        "</Types>", '<Override PartName="/xl/externalLinks/externalLink1.xml" ContentType='
        '"application/vnd.openxmlformats-officedocument.spreadsheetml.externalLink+xml"/></Types>')
    parts["[Content_Types].xml"] = types.encode()
    # Excel's last values, as a workbook saved by Excel carries them
    sheet = parts["xl/worksheets/sheet1.xml"].decode()
    for ref, value in (("A1", "8.5"), ("A2", "0.85"), ("A3", "7")):
        start = sheet.index(f'r="{ref}"')
        end = sheet.index("</f>", start) + 4
        sheet = sheet[:end] + f"<v>{value}</v>" + sheet[end:]
    parts["xl/worksheets/sheet1.xml"] = sheet.encode()
    with zipfile.ZipFile(path, "w") as z:
        for n, data in parts.items():
            z.writestr(n, data)
    return path


def bring_in(wb, path, linked=None):
    got = read_workbook(path, taken={s.name for s in wb.sheets}, linked=linked)
    make_book(got, workbook_ident(path, {b.name for b in wb.books.values()}),
              path.rsplit("/", 1)[-1], False)
    with wb.transaction("Open"):
        sheets = [wb.add_sheet(s.name) for s in got.sheets]
        for sheet, imported in zip(sheets, got.sheets):
            load_sheet(sheet, imported.data)
    wb.recalculate(everything=True)
    return got, {s.name: s for s in sheets}


def linked_from(wb):
    """read_workbook's *linked*, from the books of *wb* (as the window's)."""
    from calcforge.ui.xlsximport import linked_books
    return linked_books(wb)


def test_a_link_to_a_workbook_in_the_document_reads_it_live(tmp_path):
    wb = Workbook()
    _got, first = bring_in(wb, snow(str(tmp_path / "Snow.xlsx")))
    got, second = bring_in(wb, linking(str(tmp_path / "Roof.xlsx")), linked_from(wb))
    roof = second["Sheet1 (2)"]
    assert roof.cells[(0, 0)].input == "=Sheet1!B2*10"
    assert roof.cells[(0, 0)].value == pytest.approx(8.5)
    assert roof.cells[(1, 0)].input == "=Sheet1!$B$2", "its name, as the cells it names"
    # the sheet it hasn't: Excel's last value, said
    assert roof.cells[(2, 0)].input == "7"
    assert any("Snow.xlsx" in t for t in got.left_out)
    assert roof.cells[(3, 0)].value == "[1]Sheet1!B2 is text", "text is left alone"
    wb.set_input(first["Sheet1"], 1, 1, "1.2")
    assert roof.cells[(0, 0)].value == pytest.approx(12.0), "live"


def test_a_link_to_a_workbook_not_in_the_document_keeps_excels_values(tmp_path):
    wb = Workbook()
    got, sheets = bring_in(wb, linking(str(tmp_path / "Roof.xlsx")), linked_from(wb))
    roof = sheets["Sheet1"]
    assert [roof.cells[(r, 0)].input for r in range(3)] == ["8.5", "0.85", "7"]
    assert any("Snow.xlsx" in t and "3" in t for t in got.left_out), got.left_out


def test_the_link_code_on_its_own():
    target = {"sheets": {"sheet1": "Sheet1", "loads": "Loads (2)"},
              "names": {"sk": "Sheet1!$B$2", "k": "2*Sheet1!$B$2"}}
    links = {1: "Snow.xlsx"}

    def linked(file):
        return target if file == "Snow.xlsx" else None
    assert linked_formula("[1]Loads!A1+'[1]Sheet1'!B2", links, linked) == \
        "'Loads (2)'!A1+Sheet1!B2"
    assert linked_formula("[1]!Sk*2", links, linked) == "Sheet1!$B$2*2"
    assert linked_formula("[1]!K", links, linked) == "Sheet1!K"
    assert linked_formula("[2]Sheet1!A1", links, linked) is None
    assert linked_formula('"[1]Sheet1!A1"&A2', links, linked) == '"[1]Sheet1!A1"&A2'


def test_text_a_renamed_workbooks_formula_builds_reads_its_own_sheet(tmp_path):
    def loads(path, value):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Loads"
        ws["A1"] = value
        ws["B1"] = '=INDIRECT("Loads!A1")*2'
        ws["B2"] = '=INDIRECT("\'"&"Loads"&"\'!A1")'
        wb.save(path)
        return path
    wb = Workbook()
    _got, one = bring_in(wb, loads(str(tmp_path / "One.xlsx"), 3))
    _got, two = bring_in(wb, loads(str(tmp_path / "Two.xlsx"), 5))
    assert one["Loads"].cells[(0, 1)].value == pytest.approx(6)
    assert two["Loads (2)"].cells[(0, 1)].value == pytest.approx(10), "its own Loads"
    assert two["Loads (2)"].cells[(1, 1)].value == pytest.approx(5)
    # renamed again here: still its own
    roof = two["Loads (2)"]
    wb.rename_sheet(roof, "Roof loads")
    assert wb.books[roof.book].renamed == {"Loads": "Roof loads"}
    assert roof.cells[(0, 1)].value == pytest.approx(10)


def test_a_1904_workbook_keeps_its_dates(tmp_path):
    from openpyxl.utils.datetime import CALENDAR_MAC_1904
    path = str(tmp_path / "Mac.xlsx")
    book = openpyxl.Workbook()
    book.epoch = CALENDAR_MAC_1904
    ws = book.active
    ws["A1"] = datetime.date(2026, 10, 24)
    ws["A1"].number_format = "yyyy-mm-dd"
    ws["A2"] = "=A1+1"
    book.save(path)
    wb = Workbook()
    _got, sheets = bring_in(wb, path)
    sheet = next(iter(sheets.values()))
    wb.set_input(sheet, 2, 0, "=DATE(2026,10,24)")
    assert sheet.cells[(0, 0)].value == sheet.cells[(2, 0)].value, "the same day"
    assert sheet.cells[(1, 0)].value == pytest.approx(sheet.cells[(2, 0)].value + 1)


def test_cells_copied_to_another_workbook_bring_their_names(tmp_path):
    wb = Workbook()
    _got, snowy = bring_in(wb, snow(str(tmp_path / "Snow.xlsx")))
    _got, other = bring_in(wb, snow(str(tmp_path / "Other.xlsx")))
    source, target = snowy["Sheet1"], other["Sheet1 (2)"]
    wb.set_input(source, 4, 0, "=Sk*2")
    wb.define_name("Gamma", "1.35", home=source)
    wb.set_input(source, 5, 0, "=Gamma")
    data = clip.block_data(source, 4, 0, 5, 0)
    with wb.transaction("Paste"):
        brought, kept = clip.bring_names(wb, source, target, data)
        clip.paste(wb, target, 4, 0, data)
    assert brought == ["Gamma"] and kept == ["Sk"], "Other.xlsx has its own Sk"
    assert target.cells[(4, 0)].value == pytest.approx(1.7), "its own Sk"
    assert target.cells[(5, 0)].value == pytest.approx(1.35)
    assert wb.names[("gamma", target.book)].refers_to == "1.35"
