"""SMath Studio's own example files, put on a CalcForge page and calculated
by the window, give the answers SMath saved in them.

SMath itself can't run here, so its saved results are the reference: every
equation of each example becomes an equation item on a page (at its place,
one SMath pixel = 0.75 pt), the document's sheet calculates them in reading
order as the app always does, and every numeric result SMath stored is
compared with the value the app now holds for that equation.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF

from calcforge.calc.docsheet import PT_PER_PX, sheet_for
from calcforge.calc.engine.units import Quantity
from calcforge.calc.record import region_to_data
from calcforge.items.calc import CalcItem
from tests.calc.smfile import load_sm
from tests.calc.test_smfiles import EXAMPLES, SYMBOLIC, _close, stored_results

BOOK = EXAMPLES.parent / "book"


def _files():
    found = sorted(p for p in EXAMPLES.glob("*.sm") if p.name not in SYMBOLIC)
    found += sorted(BOOK.glob("*.sm"))           # SMath's own manual, with its results
    return found


@pytest.mark.skipif(not EXAMPLES.exists(), reason="SMath Studio examples not present")
@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name)
def test_an_smath_example_calculates_the_same_on_a_calcforge_page(window, path: Path):
    from calcforge.calc.engine.evaluator import Context, Evaluator
    from calcforge.calc.engine.parser import parse_row

    loaded = load_sm(path)
    frame = window.document.pages[0].frame
    by_place = {}
    sheet = sheet_for(window.document)
    with sheet.batch():
        for region in loaded.ordered():
            if region.kind != "math":
                continue
            item = CalcItem(region_to_data(region))
            frame.add_markup(item, QPointF(region.x * PT_PER_PX, region.y * PT_PER_PX))
            by_place[(region.y, region.x)] = item
    compared = 0
    for top, left, stored in stored_results(path):
        item = by_place.get((top, left))
        assert item is not None, (path.name, top, left)
        r = item.region
        assert r.error is None, (path.name, item.text(), r.error.message)
        shown = r.value
        if not r.editor.unit.is_empty():
            u = Evaluator().eval(parse_row(r.editor.unit), Context())
            shown = Quantity(r.value.value / u.value) if isinstance(r.value, Quantity) else r.value
        if isinstance(shown, Quantity):
            shown = Quantity(shown.value)
        if isinstance(stored, Quantity) and isinstance(shown, Quantity):
            assert _close(shown, stored), (path.name, item.text(), shown, stored)
            compared += 1
    assert compared == sum(1 for _t, _l, v in stored_results(path) if isinstance(v, Quantity))
