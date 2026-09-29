"""The autocomplete list must equal SMath Cloud's, item for item and in order.

The fixture holds lists read back from smath.com for several prefixes, with
some variables defined above the region being edited.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from websmath.ui.worksheet_view import suggestion_list  # noqa: E402
from websmath.worksheet import Worksheet  # noqa: E402

DATA = json.loads((Path(__file__).parent / "data" / "smath_suggestions.json").read_text(encoding="utf-8"))
CASES = [(group, pf) for group in DATA for pf in DATA[group]["lists"]]


@pytest.mark.parametrize("group,prefix", CASES)
def test_suggestions_match_smath(group, prefix):
    ws = Worksheet()
    for k, d in enumerate(DATA[group]["defs"]):
        r = ws.add_region(18, 9 + 36 * k)
        r.editor.type(d)
        ws.update_after_edit(r)
    # the site test typed each prefix in a region to the right of the list,
    # one row per prefix: only definitions above it are offered
    row = list(DATA[group]["lists"]).index(prefix) if group == "with_defs" else 20
    here = ws.add_region(400, 9 + 36 * row)
    got = [label for label, _ in suggestion_list(prefix, ws._context_before(here).names())]
    assert got == DATA[group]["lists"][prefix]


def _entries(prefix, defs=()):
    from websmath.ui.worksheet_view import suggestion_entries

    ws = Worksheet()
    for k, d in enumerate(defs):
        r = ws.add_region(18, 9 + 36 * k)
        for k2 in d if isinstance(d, list) else list(d):
            r.editor.key(k2)
        ws.update_after_edit(r)
    ctx = ws._context_before(ws.add_region(18, 900))
    return suggestion_entries(prefix, ctx.names(), ctx.function_arities())


def test_entries_carry_icon_kind_origin_and_description():
    es = {e.name: e for e in _entries("s", ["s1:1", ["s", "q", "(", "x", "RIGHT", ":", "x"]])}
    assert (es["'s"].text, es["'s"].kind, es["'s"].origin, es["'s"].description) == ("s", "unit", 1, "Second")
    assert (es["sin"].kind, es["sin"].origin) == ("function", 1)
    assert es["sin"].description.startswith("<strong>sin</strong>(")
    assert (es["sum (4)"].kind, es["sum (4)"].origin, es["sum (4)"].args) == ("function", 2, 4)
    assert (es["s1"].kind, es["s1"].origin, es["s1"].description) == ("operand", 3, "")
    assert (es["sq"].kind, es["sq"].origin, es["sq"].args) == ("function", 3, 1)


@pytest.mark.parametrize("prefix,defs,selected", [
    ("m", ["m:10"], "'m"),       # the unit is highlighted, the variable is listed too
    ("M", ["m:10"], "'MB"),      # case-sensitive start first
    ("Si", [], "sign"),          # else ignoring case
    ("co", [], "col"),
    ("sq", [], "sqrt"),
    ("ln", [], "ln"),
    ("e", [], "'e"),
    ("q", ["qq:1"], "qq"),
    ("x", ["x:1"], "x"),
])
def test_initial_selection_matches_smath(prefix, defs, selected):
    from websmath.ui.worksheet_view import selected_index

    es = _entries(prefix, defs)
    k = selected_index(es, prefix)
    assert es[k].name == selected
    if prefix == "m":
        assert [(e.name, e.origin) for e in es if e.text == "m"] == [("'m", 1), ("m", 3)]
