"""The autocomplete list must equal SMath Cloud's, item for item and in order.

The fixture holds lists read back from smath.com for several prefixes, with
some variables defined above the region being edited.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from websmath.ui.worksheet_view import SITE_HIDDEN_UNITS, suggestion_list  # noqa: E402
from websmath.worksheet import Worksheet  # noqa: E402

DATA = json.loads((Path(__file__).parent / "data" / "smath_suggestions.json").read_text(encoding="utf-8"))
CASES = [(group, pf) for group in DATA for pf in DATA[group]["lists"]]


@pytest.fixture
def smath_order(monkeypatch):
    import websmath.ui.worksheet_view as wv

    monkeypatch.setattr(wv, "SMATH_ORDER", True)


@pytest.mark.parametrize("group,prefix", CASES)
def test_suggestions_match_smath(group, prefix, smath_order):
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
    # the replica also lists the units the site hides behind a case variant,
    # and SI-prefixed units SMath's library lacks (hPa, daN, kWh...)
    from websmath.engine.extra_units import ADDED

    from websmath.engine.extra_functions import EXTRA_FUNCTIONS

    extra = SITE_HIDDEN_UNITS | set(ADDED)
    got = [x for x in got if x.split(" ")[0] not in EXTRA_FUNCTIONS]  # symbolic() is not an SMath function
    assert [x for x in got if not x.startswith("'") or x[1:] not in extra] == DATA[group]["lists"][prefix]


@pytest.mark.parametrize("word,unit", [("kn", "'kN"), ("mn", "'mN"), ("mpa", "'MPa"), ("kpa", "'kPa"),
                                       ("hpa", "'hPa"), ("dan", "'daN"), ("kwh", "'kWh"), ("mbar", "'mbar"),
                                       ("pa", "'Pa"), ("gpa", "'GPa")])
def test_every_unit_is_offered(word, unit):
    assert unit in [label for label, _ in suggestion_list(word, [])]


def test_case_variant_units_are_listed():
    labels = [label for label, _ in suggestion_list("kn", [])]
    assert labels.index("'kn") < labels.index("'kN")
    assert "'Pa" in [label for label, _ in suggestion_list("pa", [])]


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
    ("M", ["m:10"], "'MA"),      # case-sensitive start first (site: MB; MA is added here)
    ("Si", [], "sign"),          # else ignoring case
    ("co", [], "col"),
    ("sq", [], "sqrt"),
    ("ln", [], "ln"),
    ("e", [], "'e"),
    ("q", ["qq:1"], "qq"),
    ("x", ["x:1"], "x"),
])
def test_initial_selection_matches_smath(prefix, defs, selected, smath_order):
    from websmath.ui.worksheet_view import selected_index

    es = _entries(prefix, defs)
    k = selected_index(es, prefix)
    assert es[k].name == selected
    if prefix == "m":
        assert [(e.name, e.origin) for e in es if e.text == "m"] == [("'m", 1), ("m", 3)]


def test_default_order_variables_units_constants_functions():
    es = [e.name for e in _entries("m", ["m:10", "mass:5"])]
    assert es[:2] == ["m", "mass"]                           # the worksheet's names
    last_unit = es.index("'μm")
    assert all(n.startswith("'") for n in es[2:last_unit + 1])  # then units
    assert es.index("'m.e") > last_unit                      # then constants
    assert es.index("matrix") > es.index("'m.e")             # then functions
