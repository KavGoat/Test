"""A working session in the real window, start to finish, the way someone
would use CalcForge: the Markup | Calc switch clicked, equations typed with
units, a calculation block made self-contained, a page scale set, a length
measured and named L_beam (kept as SMath's L.beam), used in an equation, the
Variables and Maths panels used, saved and opened again — the results checked
at every stage. (Written from the session run on 2026-10-01.)"""
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog
from calcforge.calc.docsheet import sheet_for
from calcforge.calc.engine.display import display_text
from tests.test_usability import click, drag

def pump(n=4):
    for _ in range(n): QApplication.instance().processEvents()

def snap(window, name):
    pump()

def type_keys(window, *keys):
    vp = window.view.viewport()
    for k in keys:
        if isinstance(k, str):
            for ch in k: QTest.keyClicks(vp, ch)
        else:
            QTest.keyClick(vp, k)
    pump()

def at(window, x, y):
    return window.document.pages[0].frame.mapToScene(QPointF(x, y))

def click_page(window, x, y):
    p = at(window, x, y); click(window.view, p.x(), p.y()); pump()

def results(window):
    items = getattr(sheet_for(window.document), "items", {})
    out = []
    for it in sorted(items.values(), key=lambda i: (i.region.y, i.region.x)):
        r = it.region
        shown = r.error.message if r.error else (display_text(r.display) if r.display is not None else "")
        out.append((it.text(), shown))
    return out

def test_session(window, monkeypatch, tmp_path):
    window.show(); window.resize(1600, 1000); pump()
    window.view.set_zoom(1.0)
    snap(window, "00_start")
    # the switch, clicked like a person would
    QTest.mouseClick(window.mode_switch.calc, Qt.LeftButton); pump()
    assert window.view.calc.mode == "calc"
    lines = [(60, 80, "b:300'mm"), (60, 110, "h:600'mm"), (60, 140, "A:b*h="),
             (60, 170, "M:120'kN*'m"), (60, 200, "Z:b*h^2"), (60, 230, ""),
             ]
    for x, y, keys in lines:
        if not keys: continue
        click_page(window, x, y); type_keys(window, keys, Qt.Key_Return)
    # a section modulus divided properly: Z = b h²/6 ; stress
    click_page(window, 60, 200); 
    snap(window, "01_typed")
    click_page(window, 300, 80); type_keys(window, "s:M/(Z/6", Qt.Key_Right, Qt.Key_Right, "=", Qt.Key_Return)
    click_page(window, 300, 160); type_keys(window, "t:A+1=", Qt.Key_Return)
    click_page(window, 300, 200); type_keys(window, "t=", Qt.Key_Return)
    snap(window, "02_more")

    # a block round two of them, self-contained
    window.view.calc.leave()
    window.toggle_calc_mode(False)
    items = sorted(getattr(sheet_for(window.document), "items", {}).values(), key=lambda i: i.region.y)
    window.view.scene().clearSelection()
    for it in items[3:5]: it.setSelected(True)
    window.insert_block(); pump()
    blocks = [i for i in window.view.scene().items() if type(i).__name__ == "CalcBlockItem"]
    window.set_block_self_contained(blocks, True); pump()
    snap(window, "03_block")
    # scale, measure, name it, use it
    from calcforge.core.document import PageScale
    window.current_page().scale = PageScale.from_ratio(50); window.apply_scale_change()
    window.select_tool("measure_length")
    a, b = at(window, 120, 500), at(window, 420, 500)
    drag(window.view, a.x(), a.y(), b.x(), b.y()); pump()
    window.select_tool("select")
    from calcforge.items.measure import MeasureItem
    measure = [i for i in window.view.scene().items() if isinstance(i, MeasureItem)][0]
    from PySide6.QtWidgets import QLineEdit
    menu = window.build_context_menu(measure, measure.sceneBoundingRect().center())
    field = menu.findChild(QLineEdit, "measureVariable")      # typed in the menu itself
    field.setText("L_beam"); field.returnPressed.emit(); pump()
    window.toggle_calc_mode(True)
    click_page(window, 60, 560); type_keys(window, "L.beam=", Qt.Key_Return)
    click_page(window, 60, 600); type_keys(window, "w:L.beam*2'kN/'m", Qt.Key_Right, Qt.Key_Right, "=", Qt.Key_Return)
    window.view.calc.leave()
    snap(window, "04_measure")
    assert measure.variable == "L.beam"
    # panels
    window.show_panel("dock_variables", True); window.variables_panel.refresh(); pump()
    snap(window, "05_variables")
    window.show_panel("dock_maths", True); pump()
    click_page(window, 300, 300); 
    QTest.mouseClick(window.maths_panel.section("Arithmetic").button("π"), Qt.LeftButton)
    type_keys(window, "*2=", Qt.Key_Return)
    snap(window, "06_maths")
    before_saving = results(window)
    # save and reopen
    path = str(tmp_path / "session.pdf")
    window.document.path = path; assert window.save_document()
    window.open_path(path); window.current_index = 0; window.rebuild_scenes()
    window.view.fit_page(); pump(6)
    import time
    for _ in range(20): pump(); time.sleep(0.1)
    sheet_for(window.document).settle(); pump()
    snap(window, "07_reopened")
    final = dict(results(window))
    assert final["A≔b*h="] == "0.18 m^2"
    assert final["t≔A+1="] == "Units don't match."
    assert final["L.beam="] == "5.2924 m"
    assert final["w≔L.beam*2('kN)/('m)="] == "10.5848 kN"
    assert final["π*2="] == "6.2832"
    assert final == dict(before_saving)
