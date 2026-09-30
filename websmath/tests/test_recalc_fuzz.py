"""The fast incremental recalculation must give exactly the results of a full
recalculation, whatever is edited, moved or deleted.

Random worksheets (numbers with units, chains, functions, redefinitions,
round() cut-offs, evaluations) get random edits; after every edit each
region's shown result and error is compared with a fresh worksheet built
from the same regions and calculated from scratch.
"""
from __future__ import annotations

import copy
import random

import pytest

from websmath.engine.display import display_text
from websmath.worksheet import Worksheet

UNITS = ["", "'kN", "'m", "'mm", "'kPa", "'s", "'N", "'Pa"]
# units of size 1: swapping one for another keeps the number and changes
# only the unit, which the recalculation must still pass on
UNIT_SWAPS = ["", "'m", "'s", "'N", "'Pa", "'kg"]


def _template(rng: random.Random, i: int, names: list, funcs: list) -> list:
    """Keystrokes of one random region."""
    n = lambda: str(rng.randint(1, 9))
    pick = lambda: rng.choice(names) if names else n()
    kinds = ["num", "num", "chain", "chain", "sum", "func", "call", "round", "eval", "redef",
             "vec", "index", "dyn", "unitbox", "lazy"]
    kind = rng.choice(kinds)
    name = f"v{i}"
    if kind == "num":
        return list(f"{name}:{n()}{rng.choice(UNITS)}")
    if kind == "chain":
        return list(f"{name}:{pick()}*{n()}")
    if kind == "sum":
        return list(f"{name}:{pick()}+{pick()}")
    if kind == "func":
        return list(f"f{i}(x") + ["RIGHT"] + list(f":x*{pick()}")
    if kind == "call" and funcs:
        return list(f"{name}:{rng.choice(funcs)}({pick()}") + ["RIGHT"]
    if kind == "round":
        return list(f"{name}:round({pick()}") + list(",0") + ["RIGHT"]
    if kind == "vec":
        return list(f"{name}:stack({pick()},{pick()}") + ["RIGHT"]
    if kind == "index" and names:
        return list(f"{name}:{pick()}") + ["["] + list("1") + ["RIGHT"]
    if kind == "dyn":
        return list(f"{name}:eval({pick()}") + ["RIGHT"]
    if kind == "unitbox":
        return list(f"{pick()}*{n()}'kN=")
    if kind == "lazy":
        return list(f"{name}:q{rng.randint(0, 3)}+{pick()}")  # q0..q3 may be defined later
    if kind == "redef" and names:
        t = rng.choice(names)
        return list(f"{t}:{t}+{n()}")
    return list(f"{pick()}+{pick()}=")


def _fresh_results(ws: Worksheet) -> list:
    """Results of a from-scratch calculation of the same regions."""
    fresh = Worksheet()
    fresh.format = copy.deepcopy(ws.format)
    for r in ws.ordered():
        fresh.add_region(r.x, r.y, copy.deepcopy(r.editor))
    fresh.calculate()
    return _results(fresh)


def _results(ws: Worksheet) -> list:
    return [((r.y, r.x), r.editor.root.text(), display_text(r.display) if r.display is not None else None,
             r.error.message if r.error else None) for r in ws.ordered()]


def _type(region, keys) -> None:
    ed = region.editor
    ed.root.items.clear()
    ed.evaluate = False
    ed.unit.items.clear()
    ed.set_cursor(ed.root, 0)
    for k in keys:
        ed.key(k)


@pytest.mark.parametrize("seed", range(40))
def test_incremental_equals_full_recalculation(seed):
    rng = random.Random(seed)
    ws = Worksheet()
    names, funcs = [], []
    regions = []
    for i in range(rng.randint(8, 25)):
        keys = _template(rng, i, names, funcs)
        r = ws.add_region(18 + 180 * rng.randint(0, 2), 9 + 27 * i)
        _type(r, keys)
        ws.update_after_edit(r)
        regions.append(r)
        text = "".join(k for k in keys if len(k) == 1)
        if text.startswith(f"v{i}:"):
            names.append(f"v{i}")
        if rng.random() < 0.1:
            names.append(f"q{rng.randint(0, 3)}")  # names defined later on
        elif text.startswith(f"f{i}("):
            funcs.append(f"f{i}")
    assert _results(ws) == _fresh_results(ws)
    for step in range(25):
        action = rng.random()
        r = rng.choice(regions)
        text = r.editor.root.text()
        if action < 0.15 and text.startswith("v") and "≔" in text and text.split("≔")[1].isdigit():
            # same number, different unit: v3:5 -> v3:5'm
            _type(r, list(text.replace("≔", ":")) + list(rng.choice(UNIT_SWAPS)))
            ws.update_after_edit(r)
        elif action < 0.6:
            i = regions.index(r)
            _type(r, _template(rng, i, names, funcs))
            ws.update_after_edit(r)
        elif action < 0.85:
            r.y = 9 + 27 * rng.randint(0, len(regions))  # dragged elsewhere
            ws.invalidate_order()
            ws.update_after_edit(r)
        elif len(regions) > 3:
            ws.remove_region(r)
            ws.region_removed(r)
            regions.remove(r)
        assert _results(ws) == _fresh_results(ws), f"seed {seed}, step {step}"


def test_unit_change_alone_is_passed_on():
    ws = Worksheet()
    a = ws.add_region(18, 9)
    _type(a, list("x:5"))
    ws.update_after_edit(a)
    b = ws.add_region(18, 36)
    _type(b, list("y:x*2"))
    ws.update_after_edit(b)
    c = ws.add_region(18, 63)
    _type(c, list("y="))
    ws.update_after_edit(c)
    for unit, shown in (("'m", "10 m"), ("'s", "10 s"), ("'N", "10 N"), ("", "10")):
        _type(a, list("x:5" + unit))
        ws.update_after_edit(a)
        assert display_text(c.display) == shown
