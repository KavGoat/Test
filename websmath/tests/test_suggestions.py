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
