"""Name tags (2026-10-14): a named cell or block, a table and a sheet carry
a small tag with the name at their top-left corner, printed too, so a
printed page says what each is; View ▸ Name Tags hides them. Only cells
named as CalcForge variables are tagged; a spreadsheet's own names are the
sheet's (Sheet.Name) and carry none (the user, 2026-10-21)."""
from __future__ import annotations

import pytest

from calcforge.items import nametags
from tests.test_sheet_pages import paper, sheet_page
from tests.test_table_names import put
from tests.test_tables import frame, make_table, pump


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    assert window.document.settings.show_name_tags, "on to begin with"
    return window


def drawn(monkeypatch):
    seen = []
    real = nametags.draw_tag

    def spy(painter, at, text, points, above=False):
        seen.append(text)
        return real(painter, at, text, points, above)
    monkeypatch.setattr(nametags, "draw_tag", spy)
    return seen


def test_a_table_and_its_named_cells_print_their_names(w, monkeypatch):
    table = make_table(w, width=48 * 3, height=15 * 4)
    put(table, "A1", "Load")
    put(table, "B2", "10")
    wb = table.sheet.workbook
    wb.define_name("W_dead", f"{table.name}!$B$2", variable=True)
    wb.define_name("Spans", f"{table.name}!$A$3:$C$3", variable=True)
    wb.define_name("Excel_only", f"{table.name}!$C$2")
    assert [n for n, _b in nametags.named_blocks(table.sheet)] == ["W_dead", "Spans"]
    w.view.tables.close()
    pump()
    seen = drawn(monkeypatch)
    page = frame(w)
    before = paper(page)
    assert {table.name, "W_dead", "Spans"} <= set(seen)
    assert "Excel_only" not in seen, "a spreadsheet's own name has no tag"
    # the table's tag sits just above its top-left corner, on the paper
    box = table.mapRectToParent(table.local_rect()).toRect()
    ink = sum(1 for x in range(box.left(), box.left() + 30) for y in range(box.top() - 9, box.top() - 1)
              if before.pixelColor(x, y).lightness() < 200)
    assert ink > 10, "the table's name is printed above it"
    # View ▸ Name Tags off: none of them
    seen.clear()
    w.act_name_tags.trigger()
    assert w.document.settings.show_name_tags is False
    after = paper(page)
    assert seen == []
    ink = sum(1 for x in range(box.left(), box.left() + 30) for y in range(box.top() - 9, box.top() - 1)
              if after.pixelColor(x, y).lightness() < 200)
    assert ink == 0


def test_a_sheet_prints_its_name_on_its_first_page_and_its_named_cells(w, monkeypatch):
    run = sheet_page(w)
    wb = run.sheet.workbook
    wb.set_input(run.sheet, 4, 1, "25")
    wb.define_name("fck", f"'{run.sheet.name}'!$B$5", variable=True)
    wb.define_name("fyk", f"'{run.sheet.name}'!$B$6")
    pump()
    seen = drawn(monkeypatch)
    paper(run.run_frames()[0])
    assert run.sheet.name in seen and "fck" in seen and "fyk" not in seen
    # on screen too
    seen.clear()
    w.view.viewport().repaint()
    pump()
    assert run.sheet.name in seen
