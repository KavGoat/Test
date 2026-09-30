"""The record an equation is saved in gives back exactly the same equation.

Checked two ways: every region of SMath's own example worksheets, rebuilt from
its record into a fresh worksheet, shows the same input and the same result;
and random typing, round-tripped, keeps the same tree, unit box and options.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from markforge.calc.engine.display import display_text
from markforge.calc.engine.numformat import NumberFormat
from markforge.calc.editor import MathEditor
from markforge.calc.record import (add_region_from_data, editor_from_data, region_text,
                                   region_to_data, row_from_data, row_to_data)
from markforge.calc.worksheet import Worksheet
from tests.calc.smfile import load_sm
from tests.calc.test_editor_fuzz import KEYS

EXAMPLES = Path(__file__).resolve().parents[2] / "SMath Studio" / "examples"


def _shown(region) -> str:
    if region.error is not None:
        return "error: " + str(region.error)
    return "" if region.display is None else display_text(region.display)


def _rebuilt(ws: Worksheet) -> Worksheet:
    again = Worksheet()
    again.format = ws.format
    for region in ws.ordered():
        if region.special or region.field_code:
            continue
        data = json.loads(json.dumps(region_to_data(region)))   # really through JSON
        add_region_from_data(again, region.x, region.y, data)
    again.calculate()
    return again


@pytest.mark.skipif(not EXAMPLES.exists(), reason="SMath Studio examples not present")
@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.sm")), ids=lambda p: p.name)
def test_every_example_region_survives_its_record(path):
    ws = load_sm(path)
    ws.calculate()
    again = _rebuilt(ws)
    before = [r for r in ws.ordered() if not r.special and not r.field_code]
    after = again.ordered()
    assert len(before) == len(after)
    for a, b in zip(before, after):
        assert (a.editor.kind, a.editor.root.text(), a.editor.unit.text(), a.editor.text) == \
               (b.editor.kind, b.editor.root.text(), b.editor.unit.text(), b.editor.text)
        assert _shown(a) == _shown(b), a.editor.root.text()
        assert (a.fmt, a.plot, a.enabled, a.ignore_units, a.show_input) == \
               (b.fmt, b.plot, b.enabled, b.ignore_units, b.show_input)


def _typed(seed: int) -> MathEditor:
    rng = random.Random(seed)
    ed = MathEditor()
    for _ in range(rng.randint(1, 30)):
        k = rng.choice(KEYS)
        if len(k) > 1 and k not in ("LEFT", "RIGHT", "UP", "DOWN", "HOME", "END", "BACK", "DELETE", "TAB"):
            ed.type(k)
        else:
            ed.key(k)
    return ed


@pytest.mark.parametrize("seed", range(400))
def test_random_typing_survives_its_record(seed):
    ws = Worksheet()
    region = ws.add_region(18, 18, _typed(seed))
    region.fmt = NumberFormat(decimals=seed % 7, significant=bool(seed % 2))
    data = json.loads(json.dumps(region_to_data(region)))
    again = add_region_from_data(Worksheet(), 18, 18, data)
    a, b = region.editor, again.editor
    assert (a.kind, a.root.text(), a.unit.text(), a.text, a.evaluate) == \
           (b.kind, b.root.text(), b.unit.text(), b.text, b.evaluate)
    assert repr(a.root) == repr(b.root)
    assert again.fmt == region.fmt
    assert region_text(data) == (a.text if a.kind == "text" else a.root.text())
    # every box is linked to its rows, and every row to its box
    MathEditor._fix_parents(b.root)
    assert row_to_data(row_from_data(row_to_data(a.root))) == row_to_data(a.root)


def test_a_plot_keeps_its_view():
    ws = Worksheet()
    plot = ws.add_plot(0, 0)
    for ch in "sin(x":
        plot.editor.key(ch)
    plot.plot.ppu_x, plot.plot.pan_y, plot.plot.grid = 40.0, 12.0, False
    again = add_region_from_data(Worksheet(), 0, 0, region_to_data(plot))
    assert again.plot == plot.plot
    assert again.editor.plot_input and again.editor.root.text() == plot.editor.root.text()


def test_the_editor_is_wired_to_its_place_in_the_reading_order():
    """x= evaluates when x is defined above, and defines it otherwise."""
    ws = Worksheet()
    first = ws.add_region(0, 0)
    for ch in "x:2":
        first.editor.key(ch)
    ws.update_after_edit(first)
    below = add_region_from_data(ws, 0, 50, region_to_data(ws.add_region(0, 900)))
    assert below.editor.is_defined("x")
    above = add_region_from_data(ws, 0, -50, {"root": []})
    assert not above.editor.is_defined("x")
