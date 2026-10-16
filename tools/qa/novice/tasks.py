"""The 12 novice tasks of docs/qa/QA_PLAN.md section 3, driven through the real window.

    QT_QPA_PLATFORM=offscreen python tools/qa/novice/tasks.py [1 2 ...]

Each task plays a first-time user who knows Revu, Excel and SMath a little:
it looks where those tools put things first, records the wrong turns, counts
clicks and keys, takes screenshots at confusing moments and prints one JSON
summary per task (also appended to $NOVICE_SHOTS/results.jsonl).

The tile renderer starts spawn processes, so nothing runs at import time.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TASKS = {}


def task(n):
    def wrap(fn):
        TASKS[n] = fn
        return fn
    return wrap


def page_point(window, x, y, page=0):
    """Scene point of PDF point (x, y) on *page*."""
    from PySide6.QtCore import QPointF
    return window.document.pages[page].frame.mapToScene(QPointF(x, y))


def items_of(window, cls):
    return [i for i in window.view.scene().items() if isinstance(i, cls)]


def opened(H, pages=4):
    w = H.new_window()
    pdf = H.make_pdf(os.path.join(H.WORK, f"set{pages}.pdf"), pages)
    w.open_from_command_line(pdf)
    H.pump(5)
    return w, pdf


# ---------------------------------------------------------------------------
@task(1)
def t1(H, log):
    """Open a PDF, put a red cloud with a callout saying "check", save, reopen."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from calcforge.items.text import CalloutItem
    w, pdf = opened(H)
    log.step("open PDF (File > Open)", clicks=2)
    # Revu: Tools > Markup > Cloud+ ; toolbar has a Cloud+ button too.
    hits = H.toolbar_action(w, "cloud+", exact=True)
    log.note("toolbar buttons matching cloud+: %s" % [a.text() for _, a in hits])
    if hits:
        H.click_toolbar(w, hits[0][1], log)
    else:
        log.wrong_turn("no Cloud+ toolbar button")
        H.use_menu(w, log, "Tools > Markup > Cloud+")
    log.note("status after picking Cloud+: " + w.status_hint.text())
    a = page_point(w, 250, 250)
    b = page_point(w, 450, 400)
    H.drag(w.view, a.x(), a.y(), b.x(), b.y())
    log.step("drag the cloud", clicks=1)
    log.note("status after drag: " + w.status_hint.text())
    H.shot(w, "t1_after_cloud_drag")
    c = page_point(w, 650, 220)
    H.click(w.view, c.x(), c.y())
    log.step("click where the words go", clicks=1)
    H.pump(3)
    log.note("focus after placing text: %s" % type(H.focus_target(w)).__name__)
    H.type_into(H.focus_target(w), "check", log)
    H.shot(w, "t1_typed_check")
    # finish typing: click empty page
    e = page_point(w, 900, 700)
    H.click(w.view, e.x(), e.y())
    log.step("click off to finish", clicks=1)
    callouts = items_of(w, CalloutItem)
    log.note("callouts: %d; texts: %s" % (len(callouts), [getattr(c, "text", lambda: "")() if callable(getattr(c, "text", None)) else "" for c in callouts]))
    if not callouts:
        log.confused("no callout item after Cloud+ drag + click + type")
        return
    item = callouts[0]
    log.note("callout colour: %s" % getattr(item, "pen", lambda: None)().color().name()
             if hasattr(item, "pen") else "no pen()")
    log.note("Cloud+ comes out red by default (as Revu); Properties panel says "
             "'Callout Properties' while typing")
    # Save: Ctrl+S, as everywhere
    seen = []

    def on_save(widget):
        seen.append(H.describe(widget)[:400])
        H.widget_shot(widget, "t1_save_dialog")
        from PySide6.QtWidgets import QFileDialog
        if isinstance(widget, QFileDialog):
            widget.selectFile(os.path.join(H.WORK, "t1_saved.pdf"))
            widget.accept()
        else:
            H.close(widget)
    H.run_with_modal(lambda: H.key(w.view.viewport(), Qt.Key_S, Qt.ControlModifier),
                     on_save, 4000, log, "Ctrl+S")
    log.step("Ctrl+S", keys=1)
    log.note("dialogs on save: %s" % seen)
    log.note("status after save: " + w.status_hint.text())
    log.note("title after save: " + w.windowTitle())
    saved = w.document.path
    log.note("saved to: %s (original %s)" % (saved, pdf))
    H.shot(w, "t1_saved")
    # Reopen: File > Close, then File > Open (or Recent)
    recent = H.menu_search(w, "recent")
    log.note("recent-file entries: %s" % recent[:5])
    H.use_menu(w, log, "File > Close", handler=lambda d: (seen.append(H.describe(d)[:300]), H.close(d)))
    log.note("after close: tabs=%d title=%s" % (w.document_tabs.count(), w.windowTitle()))

    def on_open(widget):
        from PySide6.QtWidgets import QFileDialog
        seen.append(H.describe(widget)[:300])
        if isinstance(widget, QFileDialog):
            widget.selectFile(saved)
            widget.accept()
        else:
            H.close(widget)
    H.use_menu(w, log, "File > Open…", handler=on_open)
    log.step("pick the file in the Open dialog", clicks=2)
    H.pump(5)
    log.note("dialogs: %s" % seen[-2:])
    again = items_of(w, CalloutItem)
    log.note("after reopen: path=%s callouts=%d" % (w.document.path, len(again)))
    if again:
        log.note("text after reopen: %s" % again[0].text())
    H.shot(w, "t1_reopened")
    log.success = bool(again) and "check" in again[0].text()


@task(2)
def t2(H, log):
    """Measure a room's area on a scaled drawing; set the scale first if needed."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from calcforge.items.measure import MeasureItem
    w, pdf = opened(H)
    # A Revu user goes to Tools > Measure first, looking for Set Scale/Calibrate.
    measure = H.menu_items(w, "Tools")
    sub = [l for l in H.menu_search(w, "scale", "calibrat")]
    log.note("menu entries with scale/calibrate: %s" % sub)
    log.step("open Tools > Measure looking for Set Scale", clicks=2)
    panels = H.menu_items(w, "Window") + [l for l in H.menu_search(w, "measurements")]
    if not any("measurements" in l.lower() for l in panels):
        log.wrong_turn("no Measurements panel (Revu's home for the scale); Tools > Measure "
                       "has only Calibrate; Set Scale is Document > Page Scale… or the "
                       "status-bar 'Scale 1:1' button")
    # the status bar says "Scale 1:1" - a Revu user clicks it
    from PySide6.QtWidgets import QAbstractButton, QLabel
    scale_widgets = [c for c in w.statusBar().findChildren(QWidget_())
                     if c.isVisible() and "Scale" in (getattr(c, "text", lambda: "")() or "")]
    log.note("status-bar scale widgets: %s" % [(type(c).__name__, c.text()) for c in scale_widgets])
    dialog_seen = []

    def on_scale(d):
        dialog_seen.append(H.describe(d)[:700])
        H.widget_shot(d, "t2_scale_dialog")
        from calcforge.ui.dialogs import ScaleDialog
        if not isinstance(d, ScaleDialog):
            H.close(d)
            return
        combo = d.x_row.preset
        names = [combo.itemText(i) for i in range(combo.count())]
        dialog_seen.append("presets: %s" % names[:25])
        i = combo.findText("1:100")
        if i < 0:
            i = next((k for k, n in enumerate(names) if "1:100" in n), -1)
        if i >= 0:
            combo.setCurrentIndex(i)
        d.apply_button.click()
    opened_dialog = False
    if scale_widgets:
        btn = scale_widgets[0]
        log.step("click 'Scale 1:1' in the status bar", clicks=1)
        H.run_with_modal(lambda: QTest.mouseClick(btn, Qt.LeftButton), on_scale, 4000, log)
        opened_dialog = bool(dialog_seen)
        if not opened_dialog:
            log.wrong_turn("clicking 'Scale 1:1' in the status bar opened no scale dialog")
            H.shot(w, "t2_status_scale_click")
    if not opened_dialog:
        H.use_menu(w, log, "Document > Page Scale…", handler=on_scale)
    log.step("choose 1:100 from Preset, Apply Scale", clicks=3)
    log.note("scale dialog: %s" % dialog_seen)
    sc = w.document.pages[0].scale
    log.note("page scale after: %s  label=%s" % (sc.length_per_pt, sc.label))
    log.note("status scale text after: %s" % [c.text() for c in scale_widgets])
    # Area tool: Measure toolbar 'Area'
    hits = H.toolbar_action(w, "area", exact=True)
    H.click_toolbar(w, hits[0][1], log)
    log.note("hint: " + w.status_hint.text())
    corners = [(200, 200), (600, 200), (600, 500), (200, 500)]
    for k, (x, y) in enumerate(corners):
        p = page_point(w, x, y)
        if k == len(corners) - 1:
            H.double_click(w.view, p.x(), p.y())
        else:
            H.click(w.view, p.x(), p.y())
    log.step("click 3 corners, double-click the 4th", clicks=5)
    H.pump(3)
    found = items_of(w, MeasureItem)
    log.note("measure items: %s" % [(m.kind, m.summary()) for m in found])
    H.shot(w, "t2_area_done")
    from calcforge.ui.panels import PropertiesPanel
    props = H.describe(w.findChildren(PropertiesPanel)[0])
    log.note("Properties panel shows the value: %s" % ("149" in props))
    log.note("Properties fields: " + props[:1500])
    log.note("status bar: %s" % [c.text() for c in w.statusBar().findChildren(QWidget_())
                                 if c.isVisible() and hasattr(c, "text") and c.text()])
    if found:
        log.success = True
        log.note("expected about 149.3 m² (14.11 m × 10.58 m at 1:100)")


def QWidget_():
    """QWidget, imported late (nothing Qt is imported at module load)."""
    from PySide6.QtWidgets import QWidget
    return QWidget


def thumbs(w):
    from calcforge.ui.panels import PagesPanel
    return w.findChildren(PagesPanel)[0]


def thumb_menu(H, w, row, log, pick=None, label=None):
    """Right-click thumbnail *row*; pick a path of entries if given."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    lst = thumbs(w).list
    rect = lst.visualItemRect(lst.item(row))
    pos = rect.center()
    got = {}

    def h(menu):
        got["labels"] = H.menu_labels(menu)
        got["enabled"] = {H._clean(a.text()): a.isEnabled() for a in menu.actions()
                          if not a.isSeparator()}
        if pick:
            got["picked"] = H.pick_from_popup(menu, *pick)
        else:
            menu.close()
    log.step(label or f"right-click thumbnail {row + 1}", clicks=1 + (len(pick) if pick else 0))
    H.right_click_widget(lst.viewport(), pos, h)
    H.pump(3)
    return got


@task(3)
def t3(H, log):
    """Add a blank page after page 2, then delete it."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w, pdf = opened(H)
    n0 = len(w.document.pages)
    # Revu: right-click the page 2 thumbnail > Insert Pages > Insert Blank Page
    lst = thumbs(w).list
    QTest.mouseClick(lst.viewport(), Qt.LeftButton, Qt.NoModifier,
                     lst.visualItemRect(lst.item(1)).center())
    H.pump(3)
    log.step("click thumbnail 2", clicks=1)
    dialogs = []

    def on_dialog(d):
        dialogs.append(H.describe(d)[:600])
        H.widget_shot(d, "t3_dialog_%d" % len(dialogs))
        ok = H.find_button(d, "OK") or H.find_button(d, "Insert")
        if ok:
            ok.click()
        else:
            H.close(d)
    got = {}

    def menu_handler(widget):
        from PySide6.QtWidgets import QMenu
        if isinstance(widget, QMenu):
            got["labels"] = H.menu_labels(widget)
            got["enabled"] = {H._clean(a.text()): a.isEnabled() for a in widget.actions()
                              if not a.isSeparator()}
            # Revu says "Insert Pages > Insert Blank Page"; here?
            sub = [a for a in widget.actions() if H._clean(a.text()) == "Insert Blank Page"]
            if sub and sub[0].menu():
                H._fill(sub[0].menu())
                got["sub"] = H.menu_labels(sub[0].menu())
            got["picked"] = H.pick_from_popup(widget, "Insert Blank Page", "After…")
        else:
            on_dialog(widget)
    pos = lst.visualItemRect(lst.item(1)).center()
    log.step("right-click thumbnail 2", clicks=1)
    H.right_click_widget(lst.viewport(), pos, menu_handler, on_dialog)
    # the picked action runs on the next turn; dialogs it opens are caught here
    H.run_with_modal(lambda: H.pump(5), on_dialog, 3000, log)
    log.step("Insert Blank Page > After…, then OK in its dialog", clicks=3)
    log.note("thumbnail menu: %s" % got.get("labels"))
    log.note("Insert Blank Page submenu: %s" % got.get("sub"))
    n1 = len(w.document.pages)
    log.note("pages %d -> %d; dialogs: %s" % (n0, n1, dialogs))
    log.note("sizes after insert: %s" % [(round(p.setup.width_mm), round(p.setup.height_mm), p.source_note) for p in w.document.pages]
             if hasattr(w.document.pages[0].setup, "width_mm") else str(vars(w.document.pages[2].setup))[:300])
    H.shot(w, "t3_after_insert")
    new_blank = 2
    # now delete page 3 (the new one): right-click its thumbnail > Delete Page
    QTest.mouseClick(lst.viewport(), Qt.LeftButton, Qt.NoModifier,
                     lst.visualItemRect(lst.item(new_blank)).center())
    H.pump(3)
    log.step("click thumbnail 3 (the new blank)", clicks=1)
    got.clear()
    pos = lst.visualItemRect(lst.item(new_blank)).center()

    def del_handler(widget):
        from PySide6.QtWidgets import QMenu
        if isinstance(widget, QMenu):
            got["labels"] = H.menu_labels(widget)
            got["enabled"] = {H._clean(a.text()): a.isEnabled() for a in widget.actions()
                              if not a.isSeparator()}
            got["picked"] = H.pick_from_popup(widget, "Delete Pages…")
        else:
            on_dialog(widget)
    log.step("right-click thumbnail 3", clicks=1)
    H.right_click_widget(lst.viewport(), pos, del_handler, on_dialog)
    H.run_with_modal(lambda: H.pump(5), on_dialog, 3000, log)
    log.step("Delete Pages…, then OK in its dialog", clicks=2)
    n2 = len(w.document.pages)
    log.note("pages after delete: %d; dialogs: %s" % (n2, dialogs[1:]))
    if n2 != n0:
        # try the Delete key on the selected thumbnail, as in Revu
        log.wrong_turn("Delete Page from the thumbnail menu did not remove the page")
        QTest.keyClick(lst, Qt.Key_Delete)
        H.pump(3)
        log.step("Delete key on the thumbnail", keys=1)
        n2 = len(w.document.pages)
    H.shot(w, "t3_after_delete")
    log.note("left after delete: %s" % [p.source_note for p in w.document.pages])
    log.success = n1 == n0 + 1 and n2 == n0

def typing(H, w, text, log=None):
    """Type like a keyboard into whatever has focus (cell editor or canvas)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    for ch in text:
        target = H.QApplication.focusWidget() or w.view.viewport()
        if ch == "\t":
            QTest.keyClick(target, Qt.Key_Tab)
        elif ch == "\n":
            QTest.keyClick(target, Qt.Key_Return)
        else:
            QTest.keyClicks(target, ch)
        H.pump(1)
    if log:
        log.step("type %r" % text, keys=len(text))


@task(4)
def t4(H, log):
    """Make a table of three beam lengths and sum them."""
    from PySide6.QtCore import Qt
    from calcforge.items.table import TableItem
    w, pdf = opened(H)
    log.note("menu entries with 'table': %s" % H.menu_search(w, "table"))
    log.note("menu entries with 'sum': %s" % H.menu_search(w, "sum"))
    hits = H.toolbar_action(w, "table", exact=True)
    log.note("toolbar Table buttons: %s" % [(b.windowTitle(), a.toolTip()[:50]) for b, a in hits])
    if len(hits) > 1:
        log.confused("two 'Table' buttons (Calculation and Tools toolbars) - which one?")
    H.click_toolbar(w, hits[-1][1], log)
    log.note("hint: " + w.status_hint.text())
    a = page_point(w, 700, 560)
    b = page_point(w, 900, 660)
    H.drag(w.view, a.x(), a.y(), b.x(), b.y())
    log.step("drag out the table", clicks=1)
    H.pump(3)
    tables = items_of(w, TableItem)
    if not tables:
        log.confused("no table after drag")
        return
    t = tables[0]
    log.note("table %d x %d; editor open: %s; focus: %s" % (
        t.sheet.rows if hasattr(t.sheet, "rows") else -1,
        t.sheet.cols if hasattr(t.sheet, "cols") else -1,
        w.view.tables.editor is not None,
        type(H.QApplication.focusWidget()).__name__))
    log.note("hint after drag: " + w.status_hint.text())
    H.shot(w, "t4_table_drawn")
    # an Excel user just starts typing into A1
    typing(H, w, "Beam\tLength\n", log)
    typing(H, w, "B1\t4.5\n", log)
    typing(H, w, "B2\t6\n", log)
    typing(H, w, "B3\t3.2\n", log)
    typing(H, w, "Total\t=SUM(B2:B4)\n", log)
    H.pump(3)
    from calcforge.sheet.refs import parse_cell
    def val(a1):
        r = parse_cell(a1)
        return t.sheet.value(r.row, r.col)
    grid = [[str(val(f"{c}{r}")) for c in "AB"] for r in range(1, 6)]
    log.note("cells A1:B5 = %s" % grid)
    H.shot(w, "t4_table_typed")
    log.success = str(val("B5")) in ("13.7", "13.700000000000001")
    # Excel's AutoSum: Alt+= under a column of numbers
    from PySide6.QtTest import QTest
    log.note("toolbar has a Σ/AutoSum: %s" % bool(H.toolbar_action(w, "autosum", "Σ")))
    typing(H, w, "Again\t")
    QTest.keyClick(H.QApplication.focusWidget() or w.view.viewport(), Qt.Key_Equal, Qt.AltModifier)
    H.pump(2)
    QTest.keyClick(H.QApplication.focusWidget() or w.view.viewport(), Qt.Key_Return)
    H.pump(3)
    log.note("Alt+= in B6 gave input %r value %r" % (
        t.sheet.input(5, 1), t.sheet.value(5, 1)))
    if not log.success:
        log.confused("sum not 13.7: B5=%r" % val("B5"))

def equations_text(w):
    """Each equation as plain text (what copying it gives), top to bottom."""
    from calcforge.calc.record import plain_text
    from calcforge.items.calc import CalcItem
    eqs = sorted(items_of(w, CalcItem), key=lambda i: (i.scenePos().y(), i.scenePos().x()))
    out = []
    for e in eqs:
        try:
            out.append(plain_text(e.region) + ((" !! " + e.warning) if e.warning else ""))
        except Exception as exc:  # noqa: BLE001
            out.append("?%r" % exc)
    return out


def calc_keys(H, w, text, log=None):
    """Type into the canvas in Calc mode, one character at a time."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    for ch in text:
        if ch == "\n":
            QTest.keyClick(w.view.viewport(), Qt.Key_Return)
        else:
            QTest.keyClicks(w.view.viewport(), ch)
        H.pump(1)
    if log:
        log.step("type %r" % text, keys=len(text))


def new_blank(H, log=None):
    w = H.new_window()
    if log:
        H.use_menu(w, log, "File > New PDF")
    else:
        w.new_document() if hasattr(w, "new_document") else None
    H.pump(3)
    return w


@task(5)
def t5(H, log):
    """Write L:=5 m, then w:=2 kN/m, then M:=w*L^2/8= and show M in kN·m."""
    from PySide6.QtCore import Qt
    attempts = [
        ("literal task text", ["L:=5 m\n", "w:=2 kN/m\n", "M:=w*L^2/8=\n"]),
        ("SMath habit: * for units, Right arrow out of the power",
         ["L:5*m\n", "w:2*kN/m\n", "M:w*L^2\x00/8=\n"]),
        ("SMath unit quote", ["L:5'm\n", "w:2'kN/'m\n", "M:w*L^2\x00/8=\n"]),
    ]
    for k, (label, lines) in enumerate(attempts):
        w = new_blank(H, log if k == 0 else None)
        H.key(w.view.viewport(), Qt.Key_F12, log=log if k == 0 else None,
              label="F12 (Calc mode)")
        w.view.set_zoom(2.0)
        p = page_point(w, 80, 100)
        w.view.centerOn(page_point(w, 200, 200))
        H.pump(2)
        H.click(w.view, p.x(), p.y())
        if k == 0:
            log.step("click on the page", clicks=1)
        for line in lines:
            parts = line.split("\x00")
            for i, part in enumerate(parts):
                if i:
                    H.key(w.view.viewport(), Qt.Key_Right)
                calc_keys(H, w, part, log)
        H.pump(5)
        eqs = equations_text(w)
        log.note("attempt %d (%s): %s" % (k + 1, label, eqs))
        H.shot(w, "t5_attempt%d" % (k + 1))
        if any("6.25" in e and "kN" in e for e in eqs):
            log.success = True
            final = w
            break
        log.wrong_turn("attempt %d (%s) gave %s" % (k + 1, label, eqs))
    if not log.success:
        return
    # the answer: is it shown in kN·m? if not, a SMath user types the unit
    # into the placeholder after the answer.
    eqs = equations_text(final)
    log.note("answer as shown: %s" % eqs[-1])
    if "kN·m" not in eqs[-1] and "kN m" not in eqs[-1]:
        log.confused("answer not shown in kN·m: %s" % eqs[-1])

@task(6)
def t6(H, log):
    """Use a measured length as a variable in an equation."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit, QMenu
    from calcforge.items.measure import MeasureItem
    w, pdf = opened(H)
    # scale 1:100 first (known from T2): status bar Scale button
    def on_scale(d):
        from calcforge.ui.dialogs import ScaleDialog
        if isinstance(d, ScaleDialog):
            d.x_row.preset.setCurrentIndex(d.x_row.preset.findText("1:100"))
            d.apply_button.click()
        else:
            H.close(d)
    H.use_menu(w, log, "Document > Page Scale…", handler=on_scale)
    log.step("pick 1:100, Apply", clicks=2)
    hits = H.toolbar_action(w, "length", exact=True)
    H.click_toolbar(w, hits[0][1], log)
    a, b = page_point(w, 200, 200), page_point(w, 600, 200)
    H.click(w.view, a.x(), a.y())
    H.click(w.view, b.x(), b.y())
    log.step("click both ends of the top wall", clicks=2)
    H.pump(3)
    m = items_of(w, MeasureItem)
    log.note("measured: %s" % [x.summary() for x in m])
    if not m:
        log.confused("no length measurement")
        return
    item = m[0]
    # a novice right-clicks the measurement looking for "use as variable"
    item.setSelected(True)
    H.pump(2)
    c = item.mapToScene(item.boundingRect().center())
    got = {}

    def name_it(menu):
        H.widget_shot(menu, "t6_measure_menu")
        edits = menu.findChildren(QLineEdit)
        got["edits"] = [(e.placeholderText(), e.isVisible()) for e in edits]
        if edits:
            edits[0].setFocus()
            QTest.keyClicks(edits[0], "Lw")
            QTest.keyClick(edits[0], Qt.Key_Return)
            H.pump(2)
        if menu.isVisible():
            got["still_open_after_enter"] = True
            menu.close()
    labels = H.right_click_menu(w.view, c.x(), c.y(), handler=name_it, log=log,
                                label="right-click the measurement")
    log.note("measurement right-click: %s; line edits in it: %s" % (labels, got))
    if got.get("edits"):
        log.step("type 'Lw' in the menu's Variable box, Enter", keys=3)
        if got.get("still_open_after_enter"):
            log.confused("Enter in the menu's Variable box leaves the menu open")
    from calcforge.ui.panels import PropertiesPanel
    panel = w.findChildren(PropertiesPanel)[0]
    field = panel.findChild(QLineEdit, "measureVariable")
    log.note("Properties also has Variable: %s (visible without scrolling: %s)" % (
        field is not None, field is not None and not field.visibleRegion().isEmpty()))
    if not item.variable:
        log.wrong_turn("the right-click Variable box did not name it; used Properties")
        panel.ensureWidgetVisible(field)
        log.step("scroll Properties down", clicks=1)
        field.setFocus()
        QTest.keyClicks(field, "Lw")
        QTest.keyClick(field, Qt.Key_Return)
        H.pump(3)
        log.step("type 'Lw' Enter in Properties > Variable", keys=3)
    log.note("item.variable = %r" % item.variable)
    H.shot(w, "t6_variable_named")
    # Calc mode, below the room, type Lw*2=
    H.key(w.view.viewport(), Qt.Key_F12, log=log, label="F12")
    fw = H.QApplication.focusWidget()
    log.note("mode after F12: %s; focus %s (%s, editable=%s)" % (
        w.view.calc.mode, type(fw).__name__, fw.objectName(),
        getattr(fw, "isEditable", lambda: None)()))
    if w.view.calc.mode != "calc":
        log.wrong_turn("F12 did nothing: focus had moved from the Variable box to a "
                       "combo in the Properties panel")
        H.shot(w, "t6_f12_ignored")
        QTest.mouseClick(w.mode_switch.calc, Qt.LeftButton)
        H.pump(2)
        log.step("click 'Calc' on the menu bar", clicks=1)
        log.note("mode now %s; tool %s" % (w.view.calc.mode, w.view.tool_key))
    p = page_point(w, 220, 640)
    H.click(w.view, p.x(), p.y())
    log.step("click below the room", clicks=1)
    log.note("after click: focus %s hint %s" % (type(H.QApplication.focusWidget()).__name__,
                                               w.status_hint.text()))
    calc_keys(H, w, "Lw*2=\n", log)
    H.pump(5)
    eqs = equations_text(w)
    log.note("equations: %s" % eqs)
    w.view.set_zoom(1.5)
    w.view.centerOn(page_point(w, 350, 600))
    H.pump(3)
    H.shot(w, "t6_equation")
    log.success = any("28.2" in e for e in eqs)

@task(7)
def t7(H, log):
    """Insert a page break in a spreadsheet page after row 20."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMenu
    from calcforge.items.sheetpage import SheetRunItem
    from calcforge.sheet.pagination import options
    from calcforge.sheet.refs import parse_cell
    w = new_blank(H, log)
    log.note("menu bar entries with 'break': %s" % H.menu_search(w, "break"))
    log.note("menu bar entries with 'spreadsheet': %s" % H.menu_search(w, "spreadsheet"))
    H.use_menu(w, log, "Document > Insert > Spreadsheet page")
    H.pump(5)
    runs = items_of(w, SheetRunItem)
    if not runs:
        log.confused("no spreadsheet page appeared")
        return
    run = runs[0]
    log.note("pages now %d; hint: %s" % (len(w.document.pages), w.status_hint.text()))
    r = parse_cell("A21")
    pos = run.mapToScene(run.cell_rect(r.row, r.col).center())
    w.view.centerOn(pos)
    H.pump(3)
    H.click(w.view, pos.x(), pos.y())
    log.step("click cell A21", clicks=1)
    H.pump(2)
    log.note("table editor on: %s; active %s" % (w.view.tables.item is run,
                                                getattr(w.view.tables, "active", None)))
    H.shot(w, "t7_sheet_a21")
    menus = {}

    def look(menu):
        H.widget_shot(menu, "t7_cell_menu")
        menus["top"] = H.menu_labels(menu)
        for a in menu.actions():
            if a.menu():
                H._fill(a.menu())
                menus[H._clean(a.text())] = H.menu_labels(a.menu())
        # an Excel user opens Page Layout first
        if "Page Layout" in menus and "Insert Page Break" not in menus["Page Layout"]:
            menus["wrong"] = True
        H.pick_from_popup(menu, "Insert", "Insert Page Break")
    labels = H.right_click_menu(w.view, pos.x(), pos.y(), handler=look, log=log,
                                label="right-click A21")
    H.pump(3)
    log.note("cell menu: %s" % menus.get("top"))
    log.note("Page Layout submenu: %s" % menus.get("Page Layout"))
    log.note("Insert submenu: %s" % menus.get("Insert"))
    if menus.get("wrong"):
        log.wrong_turn("opened the right-click 'Page Layout' submenu first (Excel's home "
                       "for Breaks); Insert Page Break is under Insert instead")
        log.step("hover Page Layout, back out", clicks=1)
    log.step("Insert > Insert Page Break", clicks=2)
    run = items_of(w, SheetRunItem)[0]
    opts = options(run.sheet)
    log.note("breaks now: %s" % opts.get("breaks"))
    log.note("pages now %d" % len(w.document.pages))
    H.shot(w, "t7_after_break")
    log.success = 20 in (opts.get("breaks") or [])

def open_via_dialog(H, w, path, log):
    def on_open(d):
        from PySide6.QtWidgets import QFileDialog
        if isinstance(d, QFileDialog):
            d.selectFile(path)
            d.accept()
        else:
            H.close(d)
    H.use_menu(w, log, "File > Open…", handler=on_open)
    log.step("pick the file, Open", clicks=2)
    H.pump(5)


def tab_names(pane):
    bar = pane.document_tabs
    return [bar.tabText(i) for i in range(bar.count())] if bar.isVisible() else \
        ["(no tab bar) " + pane.document.title]


@task(8)
def t8(H, log):
    """Split the view, drag a document between panes, then unsplit."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    w, pdf = opened(H)
    other = H.make_pdf(os.path.join(H.WORK, "other.pdf"), 2)
    open_via_dialog(H, w, other, log)
    log.note("tabs after File > Open of a 2nd PDF: %s" % tab_names(w))
    if len(tab_names(w)) < 2:
        log.wrong_turn("File > Open replaced set4.pdf instead of opening a 2nd tab "
                       "(Revu opens each file in its own tab)")
        H.use_menu(w, log, "File > New Tab")
        open_via_dialog(H, w, pdf, log)
        log.note("tabs after File > New Tab + Open: %s" % tab_names(w))
    # Revu: Window > Split Vertical / Split Horizontal
    win_items = H.menu_items(w, "Window")
    log.step("open the Window menu (Revu's home for Split)", clicks=1)
    log.note("Window menu: %s" % win_items)
    if not any("split" in x.lower() for x in win_items):
        log.wrong_turn("Window menu has no Split (Revu 21: Window > Split Vertical/"
                       "Horizontal); found it under View > Split View")
    log.note("split entries: %s" % H.menu_search(w, "split"))
    H.use_menu(w, log, "View > Split View")
    H.pump(5)
    host = w._split_host
    if host is None:
        log.confused("View > Split View made no split")
        return
    panes = list(host.panes)
    log.note("panes: %s" % [tab_names(p) for p in panes])
    host.resize(1400, 860)
    H.pump(3)
    H.widget_shot(host, "t8_split")
    left, right = panes
    bar = left.document_tabs
    log.note("left tab bar visible: %s; right tab bar visible: %s" % (
        bar.isVisible(), right.document_tabs.isVisible()))
    # drag the first tab of the left pane onto the right pane's tab bar
    src = bar.tabRect(0).center()
    dst_bar = right.document_tabs
    target_global = dst_bar.mapToGlobal(dst_bar.rect().center()) if dst_bar.isVisible() \
        else right.view.viewport().mapToGlobal(right.view.viewport().rect().center())
    dst = bar.mapFromGlobal(target_global)
    moved_name = bar.tabText(0)
    route = os.environ.get("NOVICE_T8_ROUTE", "straight")
    log.note("drag route: %s; left tabs before: %s; active %d" % (
        route, tab_names(left), left._active_tab))
    QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, src)
    if route == "straight":
        points = [src + (dst - src) * f for f in (0.1, 0.3, 0.6, 1.0)]
    else:   # down out of the bar first, across below it, then up onto the target
        below = QPoint(src.x(), src.y() + 60)
        points = [QPoint(src.x(), src.y() + 20), below,
                  QPoint(dst.x(), below.y()), dst]
    for pt in points:
        QTest.mouseMove(bar, pt)
        H.pump(1)
    QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier, dst)
    H.pump(5)
    log.step("drag tab '%s' to the right pane" % moved_name, clicks=1)
    host = w._split_host or right._split_host
    now = [tab_names(p) for p in (host.panes if host else [])]
    log.note("after drag: %s; windows: %d" % (now, len([t for t in H.QApplication.topLevelWidgets()
                                                         if t.isVisible() and type(t).__name__ in ("MainWindow", "SplitDocumentWindow")])))
    if host:
        H.widget_shot(host, "t8_after_drag")
    dragged = bool(now) and moved_name in sum(now[1:], []) and moved_name not in now[0]
    if not dragged:
        log.confused("dragging a tab onto the other pane did not move it: %s" % now)
    # unsplit: View > Split View again (it is a toggle)
    from shiboken6 import isValid
    alive = [p for p in (left, right) if isValid(p) and p.isVisible()]
    keep = next((p for p in alive if p._split_host), alive[0] if alive else None)
    if keep is None:
        log.confused("no window left after the drag")
        return
    if keep._split_host is None:
        log.confused("the split ended by itself when the tab was dragged across")
    H.use_menu(keep, log, "View > Split View")
    H.pump(5)
    still = keep._split_host
    log.note("after unsplit: split=%s tabs=%s" % (still is not None, tab_names(keep)))
    H.shot(keep, "t8_unsplit")
    log.success = dragged and still is None

@task(9)
def t9(H, log):
    """Find every "TBC" in the document and replace it."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit, QPushButton
    from calcforge.items.text import TextItem
    from calcforge.ui.searchpanel import SearchPanel
    w, pdf = opened(H)
    # the document has "TBC" in the drawing (3x on page 1/3, 1x on 2/4) and
    # in two text-box markups a colleague left
    from calcforge.items.text import TextItem as _T
    for (x, y, words) in ((700, 650, "Footing depth TBC"), (700, 700, "Cover TBC")):
        H.click_toolbar(w, H.toolbar_action(w, "text box", exact=True)[0][1])
        p = page_point(w, x, y)
        q = page_point(w, x + 160, y + 30)
        H.drag(w.view, p.x(), p.y(), q.x(), q.y())
        H.pump(2)
        typing(H, w, words)
        e = page_point(w, 1100, 100)
        H.click(w.view, e.x(), e.y())
    H.pump(2)
    log.note("set-up text boxes: %s" % [t.text() for t in items_of(w, _T)])
    # Ctrl+H is Excel/Word's Replace; Ctrl+F is Find everywhere
    before = [d.isVisible() for d in w.findChildren(SearchPanel)]
    H.key(w.view.viewport(), Qt.Key_H, Qt.ControlModifier, log, "Ctrl+H (Replace, as Excel/Word)")
    panel = w.findChildren(SearchPanel)[0]
    log.note("after Ctrl+H: tool=%s hint=%s" % (w.view.tool_key, w.status_hint.text()))
    if not panel.isVisible():
        log.wrong_turn("Ctrl+H does not open Find/Replace")
        H.key(w.view.viewport(), Qt.Key_F, Qt.ControlModifier, log, "Ctrl+F")
    log.note("search panel visible: %s; focus: %s" % (
        panel.isVisible(), type(H.QApplication.focusWidget()).__name__))
    H.widget_shot(panel, "t9_search_panel")
    field = panel.query
    if H.QApplication.focusWidget() is not field:
        log.confused("Ctrl+F opened the Search panel but the Find box has no keyboard focus")
        QTest.mouseClick(field, Qt.LeftButton)
        log.step("click the Find box", clicks=1)
    QTest.keyClicks(field, "TBC")
    QTest.keyClick(field, Qt.Key_Return)
    H.pump(5)
    log.step("type TBC, Enter", keys=4)
    log.note("summary: %s" % panel.summary.text())
    log.note("results: %d rows" % panel.results.topLevelItemCount()
             if hasattr(panel.results, "topLevelItemCount") else "results: ?")
    H.widget_shot(panel, "t9_found")
    QTest.mouseClick(panel.replacement, Qt.LeftButton)
    QTest.keyClicks(panel.replacement, "6 m")
    log.step("click Replace with, type '6 m'", clicks=1, keys=3)
    ra = [b for b in panel.findChildren(QPushButton) if b.text() == "Replace all"][0]
    seen = []
    H.run_with_modal(lambda: QTest.mouseClick(ra, Qt.LeftButton),
                     lambda d: (seen.append(H.describe(d)[:300]), H.widget_shot(d, "t9_dialog"),
                                H.close(d)), 3000, log)
    H.pump(3)
    log.step("Replace all", clicks=1)
    log.note("dialogs: %s" % seen)
    log.note("summary after: %s; status: %s" % (panel.summary.text(), w.status_hint.text()))
    texts = [t.text() for t in items_of(w, _T)]
    log.note("text boxes after: %s" % texts)
    H.widget_shot(panel, "t9_after_replace")
    left = sum("TBC" in t for t in texts)
    log.note("TBC still in the PDF drawing (6 hits) - it is page content, cannot be replaced; "
             "Revu cannot either")
    log.success = left == 0

def add_cloud(H, w, page, log=None):
    """A red cloud on *page* (0-based), drawn with the Cloud tool."""
    w.go_to_page(page)
    H.pump(3)
    H.click_toolbar(w, H.toolbar_action(w, "cloud", exact=True)[0][1])
    a, b = page_point(w, 250, 250, page), page_point(w, 450, 400, page)
    w.view.centerOn(page_point(w, 350, 320, page))
    H.pump(2)
    H.drag(w.view, a.x(), a.y(), b.x(), b.y())
    H.pump(2)


def pdf_pages_with_red(path):
    """For each page of a written PDF: does it contain red ink (a cloud)?"""
    import fitz
    out = []
    with fitz.open(path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=30)
            red = 0
            for i in range(0, len(pix.samples) - 2, pix.n):
                r, g, b = pix.samples[i], pix.samples[i + 1], pix.samples[i + 2]
                if r > 180 and g < 90 and b < 90:
                    red += 1
            out.append(red)
    return out


@task(10)
def t10(H, log):
    """Print pages 2-3 only, without markups."""
    from PySide6.QtCore import Qt
    from PySide6.QtPrintSupport import QPrintDialog, QPrinter
    w, pdf = opened(H)
    for pg in (1, 2):
        add_cloud(H, w, pg)
    log.note("clouds on pages 2 and 3 set up")
    out = os.path.join(H.WORK, "printed.pdf")
    seen = []

    def on_print(d):
        seen.append(H.describe(d)[:900])
        H.widget_shot(d, "t10_print_dialog_%d" % len(seen))
        if isinstance(d, QPrintDialog):
            texts = H.describe(d).lower()
            if "markup" not in texts and not seen_markup_note:
                seen_markup_note.append(1)
            from PySide6.QtWidgets import QAbstractButton, QLineEdit, QSpinBox
            names = {c.objectName(): c for c in d.findChildren(QWidget_()) if c.objectName()}
            seen.append("widgets: %s" % sorted(n for n in names if not n.startswith("qt_"))[:60])
            if "filename" in names:
                names["filename"].setText(out)
            elif "outputFile" in names:
                names["outputFile"].setText(out)
            if "printRange" in names:
                names["printRange"].setChecked(True)
            if "from" in names and "to" in names:
                names["from"].setValue(2)
                names["to"].setValue(3)
            ok = [b for b in d.findChildren(QAbstractButton) if b.text().replace("&", "") == "Print"]
            ok[0].click() if ok else d.accept()
        else:
            H.close(d)
    seen_markup_note = []
    # Revu: File > Print (Ctrl+P): Pages 2-3, untick Markups
    H.run_with_modal(lambda: H.key(w.view.viewport(), Qt.Key_P, Qt.ControlModifier),
                     on_print, 6000, log, "Ctrl+P")
    log.step("Ctrl+P", keys=1)
    log.step("Pages: 2-3 in the print dialog, Print", clicks=3, keys=3)
    log.note("print dialog: %s" % seen)
    if seen_markup_note:
        log.wrong_turn("the Print dialog (Qt's own) has no Markups on/off option, "
                       "Revu's Print has a 'Markups' checkbox")
    log.note("menu entries with 'markup': %s" % H.menu_search(w, "markup"))
    log.note("menu entries with 'hide'/'show': %s" % H.menu_search(w, "hide", "show hidden"))
    first = pdf_pages_with_red(out) if os.path.exists(out) else None
    log.note("first print: pages=%s red-ink per page=%s" % (
        len(first) if first else None, first))
    # workaround a novice finds: Ctrl+A, Edit > Hide, print, Edit > Show Hidden
    if first and any(first):
        log.wrong_turn("printed WITH the clouds; tried Ctrl+A + Edit > Hide before printing")
        w.go_to_page(1)
        H.key(w.view.viewport(), Qt.Key_A, Qt.ControlModifier, log, "Ctrl+A")
        selected = len(w.view.scene().selectedItems())
        log.note("Ctrl+A selected %d items (on this page only?)" % selected)
        H.use_menu(w, log, "Edit > Hide")
        os.remove(out)
        H.run_with_modal(lambda: H.key(w.view.viewport(), Qt.Key_P, Qt.ControlModifier),
                         on_print, 6000, log, "Ctrl+P")
        log.step("Ctrl+P, Pages 2-3, Print", clicks=3, keys=4)
        second = pdf_pages_with_red(out) if os.path.exists(out) else None
        log.note("after Hide: pages=%s red-ink per page=%s" % (
            len(second) if second else None, second))
        H.use_menu(w, log, "Edit > Show Hidden")
        log.success = bool(second) and len(second) == 2 and not any(second)
        if second and any(second):
            log.confused("Ctrl+A + Hide only took the current page's markups out of the "
                         "print: %s" % second)
    else:
        log.success = bool(first) and len(first) == 2

def draw_callout(H, w, x, y, words, log=None, page=0):
    """Callout tool already in hand: click the point, drag the box, type."""
    a = page_point(w, x, y, page)
    H.click(w.view, a.x(), a.y())
    b, c = page_point(w, x + 120, y - 80, page), page_point(w, x + 240, y - 40, page)
    H.drag(w.view, b.x(), b.y(), c.x(), c.y())
    H.pump(2)
    typing(H, w, words)
    e = page_point(w, 1150, 60, page)
    H.click(w.view, e.x(), e.y())
    H.pump(2)
    if log:
        log.step("click the point, drag the box, type %r, click off" % words,
                 clicks=3, keys=len(words))


@task(11)
def t11(H, log):
    """Save a callout style and reuse it with a number key."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractSpinBox, QToolButton
    from calcforge.items.text import CalloutItem
    from calcforge.ui.panels import PropertiesPanel
    w, pdf = opened(H)
    H.click_toolbar(w, H.toolbar_action(w, "callout", exact=True)[0][1], log)
    draw_callout(H, w, 300, 650, "A", log)
    first = items_of(w, CalloutItem)
    log.note("callouts: %d" % len(first))
    item = first[0]
    # select it and make the line 3 pt in Properties
    r = item.mapToScene(item.text_rect().center()) if hasattr(item, "text_rect") else \
        item.mapToScene(item.boundingRect().center())
    H.click(w.view, r.x(), r.y())
    log.step("click the callout", clicks=1)
    log.note("selected: %s" % [type(i).__name__ for i in w.view.scene().selectedItems()])
    panel = w.findChildren(PropertiesPanel)[0]
    spin = panel.findChild(QAbstractSpinBox, "lineWidth")
    if spin is None:
        log.confused("no Line Width in Properties for the selected callout")
        return
    panel.ensureWidgetVisible(spin)
    spin.selectAll()
    spin.setFocus()
    QTest.keyClick(spin, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(spin, "3")
    QTest.keyClick(spin, Qt.Key_Return)
    H.pump(2)
    log.step("Properties > Line Width: 3", clicks=1, keys=2)
    log.note("callout width now %s" % item.style.width)
    # a Revu user right-clicks it: Add to Tool Chest? Save style?
    labels = H.right_click_menu(w.view, r.x(), r.y(), log=log, label="right-click the callout")
    log.note("callout right-click: %s" % labels)
    has_style = [l for l in labels if "style" in l.lower()]
    log.note("right-click entries naming a style: %s" % has_style)
    if not has_style:
        log.wrong_turn("right-click on the callout has no 'save as style' — only "
                       "Add to Tool Chest / Set as Default (Revu's way, but no number key)")
    # the Markup Styles toolbar
    bar = w.markup_styles.bar if hasattr(w, "markup_styles") else None
    if bar is None:
        from calcforge.ui.markupstyles import MarkupStylesBar
        bar = w.findChildren(MarkupStylesBar)[0]
    names = [b.text() or b.toolTip() for b in bar.findChildren(QToolButton) if b.isVisible()]
    log.note("Markup Styles bar now shows: %s / %s" % (
        [a.text() for a in bar.actions()][:6], names))
    H.widget_shot(bar, "t11_styles_bar")
    plus = getattr(bar, "add_button", None)
    if plus is None or not plus.isVisible():
        log.confused("no + on the Markup Styles bar")
        return
    log.note("+ tooltip: %s" % plus.toolTip())
    H.run_with_modal(lambda: QTest.mouseClick(plus, Qt.LeftButton),
                     lambda d: (log.note("dialog: " + H.describe(d)[:300]), H.close(d)), 3000, log)
    H.pump(2)
    log.step("click + on the Markup Styles bar", clicks=1)
    log.note("bar after +: %s; hint %s" % (
        [b.text() for b in bar.findChildren(QToolButton) if b.isVisible()], w.status_hint.text()))
    H.shot(w, "t11_after_plus")
    # reuse: Esc, Q, 1, draw
    H.key(w.view.viewport(), Qt.Key_Escape, log=log, label="Esc")
    e = page_point(w, 1150, 60)
    H.click(w.view, e.x(), e.y())
    QTest.keyClicks(w.view.viewport(), "q")
    H.pump(1)
    log.step("Q (Callout)", keys=1)
    QTest.keyClicks(w.view.viewport(), "1")
    H.pump(1)
    log.step("1 (style 1)", keys=1)
    log.note("after Q 1: tool %s hint %s" % (w.view.tool_key, w.status_hint.text()))
    draw_callout(H, w, 300, 780, "B", log)
    now = items_of(w, CalloutItem)
    widths = sorted((round(c.style.width, 2), c.text()) for c in now)
    log.note("callouts (width, text): %s" % widths)
    H.shot(w, "t11_reused")
    log.success = any(t == "B" and wd == 3 for wd, t in widths)

@task(12)
def t12(H, log):
    """Hide and show the Markups List; filter it to clouds only."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from calcforge.items.shapes import RectItem
    w, pdf = opened(H)
    add_cloud(H, w, 1)
    add_cloud(H, w, 2)
    w.go_to_page(0)
    H.pump(2)
    H.click_toolbar(w, H.toolbar_action(w, "rectangle", exact=True)[0][1])
    a, b = page_point(w, 650, 300), page_point(w, 800, 400)
    asked = []
    n_rect = len(items_of(w, RectItem))

    def on_rect_dialog(d):
        asked.append(H.describe(d)[:200])
        H.widget_shot(d, "t12_rectangle_asks_for_scale")
        if len(asked) == 1:
            H.close(d)                         # "I only want a box": Cancel
        else:
            apply_btn = getattr(d, "apply_button", None)
            apply_btn.click() if apply_btn else H.close(d)
    for attempt in range(3):
        H.run_with_modal(lambda: H.drag(w.view, a.x(), a.y(), b.x(), b.y()), on_rect_dialog,
                         4000, log)
        if len(items_of(w, RectItem)) > n_rect:
            break
    if asked:
        log.confused("drawing a plain Rectangle on an unscaled page opens Set Scale "
                     "every time (%d times: Cancel, then Apply 1:1, then the drag "
                     "drew)" % len(asked))
    log.note("rectangles drawn: %d after %d drags" % (
        len(items_of(w, RectItem)) - n_rect, attempt + 1))
    H.click_toolbar(w, H.toolbar_action(w, "callout", exact=True)[0][1])
    draw_callout(H, w, 300, 650, "see note")
    H.key(w.view.viewport(), Qt.Key_Escape)
    log.note("set-up: 2 clouds (p2, p3), 1 rectangle, 1 callout (p1)")
    log.note("open at start: %s" % w.markups_list_open())
    # Revu: Alt+L (or the Markups List tab at the bottom)
    H.key(w.view.viewport(), Qt.Key_L, Qt.AltModifier, log, "Alt+L")
    first = w.markups_list_open()
    H.key(w.view.viewport(), Qt.Key_L, Qt.AltModifier, log, "Alt+L")
    second = w.markups_list_open()
    H.key(w.view.viewport(), Qt.Key_L, Qt.AltModifier, log, "Alt+L")
    third = w.markups_list_open()
    log.note("Alt+L x3: open=%s, %s, %s" % (first, second, third))
    if not third:
        H.use_menu(w, log, "Window > Markups List")
    H.shot(w, "t12_list_open")
    panel = w.markups_panel
    top = panel.tree.invisibleRootItem()
    log.note("list groups top to bottom: %s" % [
        (top.child(i).text(0), top.child(i).childCount()) for i in range(top.childCount())])
    log.note("list height when opened: %d px" % panel.height())
    def rows():
        out = []
        it = panel.tree.invisibleRootItem()
        stack = [it]
        while stack:
            node = stack.pop()
            for i in range(node.childCount()):
                ch = node.child(i)
                if ch.childCount():
                    stack.append(ch)
                elif not ch.isHidden():
                    out.append(ch.text(1) or "(blank:%s|%s)" % (ch.text(0), ch.text(2)))
        return out
    log.note("rows (Type column): %s; grouped by %s" % (rows(), panel.group_by.currentText()))
    # Revu: a filter button on the column heading. Left-click the Type heading:
    header = panel.tree.header()
    col = panel.COLUMNS.index("Type")
    x = header.sectionViewportPosition(col) + header.sectionSize(col) // 2
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(x, header.height() // 2))
    H.pump(2)
    log.step("click the Type heading (Revu: filter button there)", clicks=1)
    log.note("after left-click on Type: rows %s (sorted?)" % rows())
    log.wrong_turn("left-click on the Type heading sorts; no filter button on the heading "
                   "(Revu shows a funnel on each heading)")
    # the "Filter markups…" box
    QTest.mouseClick(panel.filter, Qt.LeftButton)
    QTest.keyClicks(panel.filter, "cloud")
    H.pump(3)
    log.step("type 'cloud' in 'Filter markups…'", clicks=1, keys=5)
    via_box = rows()
    log.note("rows after typing 'cloud': %s" % via_box)
    H.shot(w, "t12_filtered_text")
    # the heading's own filter: right-click it
    panel.filter.clear()
    H.pump(2)
    got = {}

    def on_menu(menu):
        got["labels"] = H.menu_labels(menu)
        H.widget_shot(menu, "t12_header_filter_menu")
        for act in menu.actions():
            name = H._clean(act.text())
            if act.isCheckable() and act.isChecked() and name.lower() != "cloud":
                act.setChecked(False)          # each untick is a click
                got["clicks"] = got.get("clicks", 0) + 1
        menu.close()
    H.right_click_widget(header.viewport(), QPoint(x, header.height() // 2), on_menu)
    H.pump(3)
    log.step("right-click the Type heading, untick everything but Cloud",
             clicks=1 + got.get("clicks", 0))
    log.note("header filter menu: %s" % got.get("labels"))
    via_header = rows()
    log.note("rows after header filter: %s; heading now %r" % (
        via_header, panel.tree.headerItem().text(col)))
    H.shot(w, "t12_filtered_header")
    clouds_only = lambda r: r and all(t.lower() == "cloud" for t in r) and len(r) == 2
    log.success = clouds_only(via_box) or clouds_only(via_header)
    if not clouds_only(via_box):
        log.confused("the 'Filter markups…' box with 'cloud' does not give just the 2 "
                     "clouds: %s" % via_box)


def run(numbers):
    import harness as H
    out = os.path.join(H.SHOTS, "results.jsonl")
    for n in numbers:
        log = H.Log(f"T{n}")
        try:
            TASKS[n](H, log)
        except Exception:  # noqa: BLE001
            log.note("CRASH: " + traceback.format_exc()[-1500:])
        summary = log.summary()
        print(json.dumps(summary, indent=1))
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(summary) + "\n")


if __name__ == "__main__":
    if os.environ.get("NOVICE_TRACE"):
        import faulthandler
        faulthandler.dump_traceback_later(int(os.environ.get("NOVICE_TRACE")), exit=True)
    chosen = [int(a) for a in sys.argv[1:]]
    if len(chosen) == 1:
        run(chosen)
    else:
        # one process per task: windows left over from an earlier task slow
        # every later one down, which would show up as false stalls
        import subprocess
        for n in chosen or sorted(TASKS):
            subprocess.run([sys.executable, os.path.abspath(__file__), str(n)],
                           timeout=300)
