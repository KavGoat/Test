"""Equations on pages (phase 2): items on MarkForge pages, one worksheet.

Decision 9: variables reach the whole document, evaluated page 1 top-left to
bottom-right, then page 2, and so on; reordering pages changes the order.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF

from markforge.calc.docsheet import sheet_for
from markforge.calc.editor import MathEditor
from markforge.calc.engine.display import display_text
from markforge.calc.record import region_to_data
from markforge.calc.worksheet import Worksheet
from markforge.items.calc import CalcItem


def typed(keys: str) -> dict:
    """The record of an equation typed key by key, as SMath would take it."""
    ws = Worksheet()
    region = ws.add_region(0, 0, MathEditor())
    region.editor.type(keys)
    return region_to_data(region)


def put(window, page_index: int, x: float, y: float, keys: str) -> CalcItem:
    frame = window.document.pages[page_index].frame
    item = CalcItem(typed(keys))
    frame.add_markup(item, QPointF(x, y))
    return item


def shown(item: CalcItem) -> str:
    region = item.region
    if region.error is not None:
        return "error: " + str(region.error)
    return display_text(region.display) if region.display is not None else ""


def test_a_variable_on_page_one_is_known_on_page_two(window):
    window.add_page()
    put(window, 0, 60, 100, "L:7.2'm")
    use = put(window, 1, 60, 60, "L*2=")
    assert shown(use) == "14.4 m"


def test_reading_order_is_top_to_bottom_then_the_next_page(window):
    window.add_page()
    use = put(window, 0, 60, 300, "a+0=")
    put(window, 1, 60, 50, "a:3")
    assert shown(use).startswith("error")          # defined later in the document
    define = put(window, 0, 60, 100, "a:2")
    assert shown(use) == "2"
    define.setPos(QPointF(60, 400))                 # moved below its use
    sheet_for(window.document).settle()             # as the end of a drag does
    assert shown(use).startswith("error")


def test_reordering_pages_changes_the_order(window):
    window.add_page()
    use = put(window, 0, 60, 100, "b+0=")
    put(window, 1, 60, 100, "b:5")
    assert shown(use).startswith("error")
    window.document.move_page(1, 0)
    sheet_for(window.document).pages_changed()
    assert shown(use) == "5"


def test_an_equation_is_not_a_markup_in_the_pdf_sense(window):
    item = put(window, 0, 60, 100, "x:1")
    assert item.IS_CALC
    assert item.local_rect().width() > 0 and item.local_rect().height() > 0


def test_removing_an_equation_undefines_what_it_defined(window):
    define = put(window, 0, 60, 100, "c:4")
    use = put(window, 0, 60, 200, "c+0=")
    assert shown(use) == "4"
    window.document.pages[0].frame.remove_markup(define)
    assert shown(use).startswith("error")


def test_a_page_restored_from_its_record_calculates_again(window):
    put(window, 0, 60, 100, "d:6")
    use = put(window, 0, 60, 200, "d*2=")
    frame = window.document.pages[0].frame
    frame.load_items(frame.serialize_items())
    items = [i for i in frame.markups() if isinstance(i, CalcItem)]
    assert len(items) == 2
    again = max(items, key=lambda i: i.pos().y())
    assert again is not use and shown(again) == "12"


def test_moving_a_page_in_the_window_reorders_the_calculation(window):
    window.add_page()
    use = put(window, 0, 60, 100, "q+0=")
    put(window, 1, 60, 100, "q:7")
    assert shown(use).startswith("error")
    window.move_page(1, 0)
    assert shown(use) == "7"
    window.undo_something()
    use = next(i for i in window.document.pages[0].frame.markups() if isinstance(i, CalcItem))
    assert shown(use).startswith("error")


def test_deleting_a_page_takes_its_equations_out_of_the_calculation(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    window.add_page()
    put(window, 0, 60, 100, "f:8")
    use = put(window, 1, 60, 100, "f+0=")
    assert shown(use) == "8"
    window.delete_page(0)
    use = next(i for i in window.document.pages[0].frame.markups() if isinstance(i, CalcItem))
    assert shown(use).startswith("error")
