"""An imported Excel workbook is self-contained, or its names are the
document's (the user's answers by pop-up, 2026-10-19).

* Self-contained (the default): its names are its own. Its cells read them
  first (a sheet's own name wins on its sheet, as in Excel), else the
  equation variable defined above the sheet; var(X) still reads the equation
  variable. Equations below read any of its cells by sheet and cell
  (Seismic_Actions.H44) and its names only qualified: Book.Name (the
  workbook's name: its file name as an identifier, unique in the document)
  or Sheet.Name; never bare.
* Not self-contained: its names are document variables, each defined where
  its sheet is in reading order. The import lists the names that clash with
  the document's, to keep it self-contained, rename them with a prefix, or
  go ahead.
* The choice is a tick in the import chooser, changeable later from the
  sheet tab's right-click menu and the Properties panel, one undo step,
  saved with the document. Two workbooks with the same names stay apart.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

openpyxl = pytest.importorskip("openpyxl")

from openpyxl.workbook.defined_name import DefinedName  # noqa: E402

import tests.calc.test_calcforge_window as cw  # noqa: E402
from calcforge.calc.engine.display import display_text  # noqa: E402
from calcforge.items.calc import CalcItem  # noqa: E402
from calcforge.items.sheetpage import SheetRunItem  # noqa: E402
from calcforge.sheet.store import load_sheet, sheet_to_dict  # noqa: E402
from calcforge.sheet.workbook import Workbook  # noqa: E402
from calcforge.sheet.xlsx import make_book, read_workbook, workbook_ident  # noqa: E402


def quake(path: str, z: float = 0.4) -> str:
    """Two worksheets sharing the workbook name Z; Tables has its own
    ReturnPeriodFactor; B2 reads k, which the workbook doesn't name."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Seismic Actions"
    ws["A1"], ws["A2"] = z, 1.0
    ws["B2"] = "=Z*k"
    ws["B3"] = "=ReturnPeriodFactor"
    ws["B4"] = "=var(Z)"
    tables = wb.create_sheet("Tables")
    tables["A1"], tables["A2"] = 3, 1.3
    tables["B1"] = "=Z*2"
    tables["B2"] = "=ReturnPeriodFactor*2"
    wb.defined_names["Z"] = DefinedName("Z", attr_text="'Seismic Actions'!$A$1")
    wb.defined_names["ReturnPeriodFactor"] = DefinedName("ReturnPeriodFactor",
                                                         attr_text="'Seismic Actions'!$A$2")
    tables.defined_names["ReturnPeriodFactor"] = DefinedName("ReturnPeriodFactor",
                                                             attr_text="Tables!$A$2")
    wb.save(path)
    return path


# -- the engine on its own ----------------------------------------------------------------
def engine_with(*books):
    """A workbook holding each imported workbook (path, self-contained) as one."""
    wb = Workbook()
    out = []
    for path, own in books:
        got = read_workbook(path, taken={s.name for s in wb.sheets})
        make_book(got, workbook_ident(path, {b.name for b in wb.books.values()}), "", own)
        with wb.transaction("Open"):
            sheets = [wb.add_sheet(s.name) for s in got.sheets]
            for sheet, imported in zip(sheets, got.sheets):
                load_sheet(sheet, imported.data)
        out.append({s.name: s for s in sheets})
    wb.recalculate(everything=True)
    return wb, out


def test_two_self_contained_workbooks_with_the_same_names_stay_apart(tmp_path):
    a = quake(str(tmp_path / "Quake Calc.xlsx"), 0.4)
    b = quake(str(tmp_path / "Quake Calc copy.xlsx"), 0.13)
    wb, (one, two) = engine_with((a, True), (b, True))
    assert one["Tables"].cells[(0, 1)].value == pytest.approx(0.8)
    assert two["Tables (2)"].cells[(0, 1)].value == pytest.approx(0.26)
    assert sorted(b.name for b in wb.books.values()) == ["Quake_Calc", "Quake_Calc_copy"]
    # a sheet's own name wins on its sheet; the workbook's elsewhere
    assert one["Tables"].cells[(1, 1)].value == pytest.approx(2.6)
    assert one["Seismic Actions"].cells[(2, 1)].value == pytest.approx(1.0)
    # a sheet made here doesn't see a self-contained workbook's names
    plain = wb.add_sheet("Mine")
    wb.set_input(plain, 0, 0, "=Z")
    assert plain.cells[(0, 0)].value.code == "#NAME?"
    # one not self-contained: its names are the document's
    wb.set_self_contained(next(b.id for b in wb.books.values() if b.name == "Quake_Calc"), False)
    assert plain.cells[(0, 0)].value == pytest.approx(0.4)
    assert two["Tables (2)"].cells[(0, 1)].value == pytest.approx(0.26), "its own names first"


def test_a_cell_reads_its_workbooks_name_first_then_the_equation_variable(tmp_path):
    asked = []
    wb, (sheets,) = engine_with((quake(str(tmp_path / "q.xlsx")), True))

    def outside(sheet, name):
        asked.append(name)
        if name.lower() in ("k", "z"):
            return {"k": 10.0, "z": 99.0}[name.lower()]
        raise KeyError(name)
    wb.outside = outside
    wb.recalculate(everything=True)
    sa = sheets["Seismic Actions"]
    assert sa.cells[(1, 1)].value == pytest.approx(4.0), "Z the workbook's, k the equations'"
    assert sa.cells[(3, 1)].value == pytest.approx(99.0), "var(Z) is the equation variable"
    assert "k" in asked


def test_the_workbook_and_its_setting_are_saved_with_each_sheet(tmp_path):
    wb, (sheets,) = engine_with((quake(str(tmp_path / "Quake Calc.xlsx")), True))
    data = sheet_to_dict(sheets["Tables"])
    assert data["book"]["name"] == "Quake_Calc" and data["book"]["self_contained"] is True
    assert [n[:3] for n in data["names"]] == [["ReturnPeriodFactor", "Tables!$A$2", True]]
    other = Workbook()
    copy = other.add_sheet("Seismic Actions")
    load_sheet(copy, sheet_to_dict(sheets["Seismic Actions"]))
    tables = other.add_sheet("Tables")
    load_sheet(tables, data)
    other.recalculate(everything=True)
    assert tables.cells[(0, 1)].value == pytest.approx(0.8)
    assert copy.book == tables.book and other.books[copy.book].self_contained


# -- in the window --------------------------------------------------------------------------------
def pump():
    for _ in range(3):
        QApplication.instance().processEvents()


def tick(box) -> None:
    """A click on a tick box's square, where a person clicks it."""
    from PySide6.QtWidgets import QStyle, QStyleOptionButton
    option = QStyleOptionButton()
    option.initFrom(box)
    square = box.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, box)
    QTest.mouseClick(box, Qt.LeftButton, Qt.NoModifier, square.center())


def results(window) -> dict:
    return {item.region.editor.root.text(): (item.region.error.message if item.region.error else
                                             display_text(item.region.display)
                                             if item.region.display else None)
            for item in window.view.scene().items()
            if isinstance(item, CalcItem) and item.region is not None}


def runs(window) -> dict:
    return {i.sheet.name: i for i in window.view.scene().items() if isinstance(i, SheetRunItem)}


def type_equations(window, page: int, lines) -> None:
    v = cw.Sheet(window)
    v.frame = window.document.pages[page].frame
    for k, text in enumerate(lines):
        v.type_at(36, 18 + 40 * k, "")
        v.keys(text)
        v.press(Qt.Key_Return)
        v.calc.leave()
        pump()


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    return window


def with_workbook(w, path, k_first=True):
    """k:=10 on page 1, the workbook after it, a blank page after that."""
    if k_first:
        type_equations(w, 0, ["k:10"])
    assert w.insert_workbook(path, 0)
    pump()
    w.add_page(len(w.document.pages) - 1)
    pump()
    return len(w.document.pages) - 1


def test_equations_read_its_cells_and_qualified_names_never_bare(w, tmp_path):
    last = with_workbook(w, quake(str(tmp_path / "Quake Calc.xlsx")))
    type_equations(w, last, ["a:Seismic_Actions.B2", "a=", "z:Quake_Calc.Z", "z=",
                             "q:Seismic_Actions.Z", "q=", "f:Tables.ReturnPeriodFactor", "f=",
                             "y:Z"])
    got = results(w)
    assert got["a="] == "4", "B2 = Z*k, k the equation variable above the sheets"
    assert got["z="] == "0.4" and got["q="] == "0.4" and got["f="] == "1.3"
    assert got["y≔Z"] == "Z - not defined.", "a self-contained workbook's names are its own"
    assert any("Quake_Calc.Name" in line for line in w._last_import_report)
    # an input changed: the cells and the equations below follow; undone, back
    sheet = runs(w)["Seismic Actions"].sheet
    w.view.begin_snapshot([runs(w)["Seismic Actions"].parentItem()])
    sheet.workbook.set_input(sheet, 0, 0, "0.5")
    w.view.commit_snapshot("Edit cell")
    pump()
    assert results(w)["a="] == "5" and runs(w)["Tables"].sheet.cells[(0, 1)].value == 1.0
    w.undo_stack.undo()
    pump()
    assert results(w)["a="] == "4" and runs(w)["Tables"].sheet.cells[(0, 1)].value == 0.8


def test_the_sheet_tab_menu_changes_it_as_one_undo_step_and_it_is_saved(w, tmp_path):
    from tests.test_calc_saving import reopen, save_to
    last = with_workbook(w, quake(str(tmp_path / "Quake Calc.xlsx")))
    type_equations(w, last, ["y:Z", "y="])
    w.go_to_page(1)                       # the workbook view: its tabs
    pump()
    menu = w.sheet_tabs.build_menu(0)
    (tick,) = [a for a in menu.actions() if a.text() == "Self-contained"]
    assert tick.isCheckable() and tick.isChecked()
    steps = w.undo_stack.count()
    tick.trigger()
    pump()
    assert w.undo_stack.count() == steps + 1
    assert results(w)["y="] == "0.4", "its names are document variables now"
    w.undo_stack.undo()
    pump()
    assert results(w)["y≔Z"] == "Z - not defined."
    w.undo_stack.redo()
    pump()
    path = str(tmp_path / "doc.pdf")
    save_to(w, path)
    reopen(w, path)
    pump()
    pump()
    assert results(w)["y="] == "0.4"
    books = runs(w)["Tables"].sheet.workbook.books
    assert [(b.name, b.self_contained) for b in books.values()] == [("Quake_Calc", False)]
    w.go_to_page(1)
    pump()
    menu = w.sheet_tabs.build_menu(0)
    assert not [a for a in menu.actions() if a.text() == "Self-contained"][0].isChecked()


def test_the_properties_panel_ticks_it_by_mouse(w, tmp_path):
    from PySide6.QtWidgets import QCheckBox
    with_workbook(w, quake(str(tmp_path / "Quake Calc.xlsx")), k_first=False)
    run = runs(w)["Tables"]
    w.show_properties_panel()
    w.view.tables.open(run, (0, 0))
    pump()
    box = w.properties_panel.body.findChild(QCheckBox, "workbookSelfContained")
    assert box is not None and box.isChecked() and box.isVisible()
    steps = w.undo_stack.count()
    tick(box)
    pump()
    assert not run.sheet.workbook.books[run.sheet.book].self_contained
    assert w.undo_stack.count() == steps + 1


def test_unticking_later_with_clashes_asks_first(w, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from calcforge.ui.workbookscope import set_self_contained
    type_equations(w, 0, ["Z:7", "k:10"])
    with_workbook(w, quake(str(tmp_path / "Quake Calc.xlsx")), k_first=False)
    sheet = runs(w)["Tables"].sheet
    w.interactive_prompts = True
    said = []

    def answer(label):
        def exec_(box):
            said.append(box.text())
            box._clicked = next(b for b in box.buttons() if b.text() == label)
            return 0
        return exec_
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._clicked)
    monkeypatch.setattr(QMessageBox, "exec", answer("Keep self-contained"))
    assert not set_self_contained(w, sheet.book, False)
    assert "Z — an equation variable" in said[0]
    assert sheet.workbook.books[sheet.book].self_contained
    monkeypatch.setattr(QMessageBox, "exec", answer("Go ahead"))
    assert set_self_contained(w, sheet.book, False)
    assert not sheet.workbook.books[sheet.book].self_contained


def chooser_for(w, tmp_path, taken):
    from calcforge.ui.xlsximport import SheetChooser
    got = read_workbook(quake(str(tmp_path / "Quake Calc.xlsx")))
    chooser = SheetChooser(w, got, taken, "Quake_Calc")
    chooser.dialog.show()
    pump()
    return chooser


def test_the_chooser_has_the_tick_and_lists_clashes_when_unticked(w, tmp_path):
    chooser = chooser_for(w, tmp_path, {"z": "an equation variable"})
    assert chooser.self_contained.isChecked() and chooser.clash_box.isHidden()
    tick(chooser.self_contained)
    pump()
    assert not chooser.self_contained.isChecked() and chooser.clash_box.isVisible()
    assert chooser.clash_list.text() == "Z — an equation variable"
    assert chooser.prefix.text() == "Quake_" and chooser.rename_radio.isChecked()
    assert chooser.scope() == (chooser.RENAME, "Quake_")
    QTest.mouseClick(chooser.ahead_radio, Qt.LeftButton)
    assert chooser.scope() == (chooser.AHEAD, "")
    QTest.mouseClick(chooser.keep_button, Qt.LeftButton)
    pump()
    assert chooser.self_contained.isChecked() and chooser.clash_box.isHidden()
    assert chooser.scope() == (chooser.KEEP, "")
    QTest.mouseClick(chooser.buttons.button(QDialogButtonBox.Ok), Qt.LeftButton)
    assert chooser.dialog.result()


def drive(choice: str, prefix: str = ""):
    """A hand on the import chooser: untick Self-contained and choose."""
    def go(chooser):
        chooser.dialog.show()
        tick(chooser.self_contained)
        if choice == "rename":
            chooser.prefix.clear()
            QTest.keyClicks(chooser.prefix, prefix)
        elif choice == "ahead":
            QTest.mouseClick(chooser.ahead_radio, Qt.LeftButton)
        QTest.mouseClick(chooser.buttons.button(QDialogButtonBox.Ok), Qt.LeftButton)
    return go


def test_renamed_with_a_prefix_its_formulas_follow(w, tmp_path):
    type_equations(w, 0, ["Z:7", "k:10"])
    w.drive_workbook_chooser = drive("rename", "Qk_")
    last = with_workbook(w, quake(str(tmp_path / "Quake Calc.xlsx")), k_first=False)
    sa = runs(w)["Seismic Actions"].sheet
    assert sa.cells[(1, 1)].input == "=Qk_Z*k" and sa.cells[(1, 1)].value == pytest.approx(4.0)
    assert runs(w)["Tables"].sheet.cells[(1, 1)].input == "=ReturnPeriodFactor*2", \
        "a sheet's own name is left alone"
    assert any("Z → Qk_Z" in line for line in w._last_import_report)
    type_equations(w, last, ["y:Qk_Z", "y=", "zz:Z", "zz="])
    got = results(w)
    assert got["y="] == "0.4" and got["zz="] == "7"


def test_go_ahead_reading_order_decides(w, tmp_path):
    type_equations(w, 0, ["Z:7", "k:10"])
    w.drive_workbook_chooser = drive("ahead")
    last = with_workbook(w, quake(str(tmp_path / "Quake Calc.xlsx")), k_first=False)
    type_equations(w, last, ["y:Z", "y="])
    assert results(w)["y="] == "0.4", "the workbook's Z is the latest before it"
    sheet = runs(w)["Tables"].sheet
    assert not sheet.workbook.books[sheet.book].self_contained


def test_variables_panel_and_name_manager_show_the_workbook(w, tmp_path):
    from calcforge.ui.names import scope_text
    from calcforge.ui.variablespanel import table_rows
    with_workbook(w, quake(str(tmp_path / "Quake Calc.xlsx")), k_first=False)
    rows = [r for r in table_rows(w.document) if r.group]
    assert {r.name for r in rows} == {"Quake_Calc.Z", "Quake_Calc.ReturnPeriodFactor",
                                      "Tables.ReturnPeriodFactor"}
    assert not [r for r in table_rows(w.document) if r.name == "Z"], "not a document variable"
    w.variables_panel.refresh()

    def heads():
        tree = w.variables_panel.tree
        return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    # the user, 2026-10-23: only CalcForge's variables, unless Sheet Names is ticked
    assert "Workbook Quake_Calc" not in heads()
    assert not [h for h in heads() if "Quake_Calc." in h or "ReturnPeriodFactor" in h]
    w.variables_panel.sheet_names.setChecked(True)
    assert "Workbook Quake_Calc" in heads()
    assert "Quake_Calc.Z" in heads()
    w.variables_panel.sheet_names.setChecked(False)
    wb = runs(w)["Tables"].sheet.workbook
    scopes = sorted(scope_text(wb, dn) for dn in wb.names.values())
    assert scopes == ["Quake_Calc (self-contained)", "Quake_Calc (self-contained)", "Tables"]


def test_a_second_import_of_the_same_workbook_is_another_workbook(w, tmp_path):
    path = quake(str(tmp_path / "Quake Calc.xlsx"))
    with_workbook(w, path, k_first=False)
    assert w.insert_workbook(path, len(w.document.pages) - 1)
    pump()
    books = runs(w)["Tables"].sheet.workbook.books
    assert sorted(b.name for b in books.values()) == ["Quake_Calc", "Quake_Calc_2"]
    # shown as its sheets are: "Quake Calc" and "Quake Calc (2)" (the user, 2026-10-23)
    from calcforge.ui.sheetpages import sections
    assert [s.name for s in sections(w.document) if s.book] == ["Quake Calc", "Quake Calc (2)"]
    assert runs(w)["Tables (2)"].sheet.cells[(0, 1)].value == pytest.approx(0.8)
