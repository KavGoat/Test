"""Random key sequences into the equation editor: nothing may crash, the
cursor always sits at a real position, undo goes back to an empty region,
redo gives the same equation back, and parsing, calculating and laying out
whatever was typed never raises (a calculation problem must become an
error message on the region, never a crash)."""
from __future__ import annotations

import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from calcforge.calc.editor import MathEditor
from calcforge.calc.engine.model import Box, Row
from calcforge.calc.engine.parser import ParseError, parse_row
from calcforge.calc.worksheet import Worksheet
from calcforge.calc.ui.layout import Layouter, Style
KEYS = list("0123456789xyab+-*/^()[],.:='\" !") + ["LEFT","RIGHT","UP","DOWN","HOME","END","BACK","DELETE","TAB","BACK","LEFT"] + ["'kN","'m","sin(","sqrt(","if(","mat("]
def rows_of(r):
    yield r
    for it in r.items:
        if isinstance(it, Box):
            for c in it.rows:
                yield from rows_of(c)
def check(ed, where):
    if ed.kind == "text":
        assert 0 <= ed.text_pos <= len(ed.text), where
        return
    reach = list(rows_of(ed.root)) + list(rows_of(ed.unit))
    assert any(ed.row is r for r in reach), ("cursor row not in tree", where)
    assert 0 <= ed.pos <= len(ed.row.items), ("pos", where)
    for r in reach:
        for it in r.items:
            if isinstance(it, Box):
                for c in it.rows:
                    assert c.parent is it, ("parent link", where)
import logging  # noqa: E402
class _Boom(logging.Handler):
    def emit(self, record):
        raise RuntimeError("caught crash: " + record.getMessage() + " " + str(record.exc_info[1] if record.exc_info else ""))
logging.getLogger("calcforge.calc").addHandler(_Boom())
logging.getLogger("calcforge.calc").propagate = False
def run(seed):
    rng = random.Random(seed)
    ed = MathEditor()
    keys = []
    for _ in range(rng.randint(1, 30)):
        k = rng.choice(KEYS)
        keys.append(k)
        if len(k) > 1 and k not in ("LEFT","RIGHT","UP","DOWN","HOME","END","BACK","DELETE","TAB"):
            ed.type(k)
        else:
            ed.key(k)
        check(ed, keys)
    final = (ed.kind, ed.root.text() if ed.kind == "math" else ed.text)
    # undo to the start, redo to the end
    n = 0
    while ed.undo():
        n += 1
        check(ed, ("undo", keys))
    start = (ed.kind, ed.root.text() if ed.kind == "math" else ed.text)
    assert start in (("math", ""),), ("undo did not return to empty", start, keys)
    while ed.redo():
        check(ed, ("redo", keys))
    again = (ed.kind, ed.root.text() if ed.kind == "math" else ed.text)
    assert again == final, ("redo differs", final, again, keys)
    if ed.kind == "math":
        try:
            parse_row(ed.root)
        except ParseError:
            pass
        ws = Worksheet(); r = ws.add_region(18, 18, ed); ws.update_after_edit(r)
        Layouter(Style()).row(ed.root)


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.mark.parametrize("block", range(15))
def test_random_editing_is_robust(app, block):
    for seed in range(block * 100, block * 100 + 100):
        run(seed)
