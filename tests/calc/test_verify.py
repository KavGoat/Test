"""The double-check (engine/verify.py) agrees with correct results and
catches wrong ones: a wrong value, a wrong unit, a wrong display."""
from __future__ import annotations

import glob
from pathlib import Path

import pytest

from markforge.calc.engine.display import DNum, display_value
from markforge.calc.engine.numformat import format_real
from markforge.calc.engine.units import Quantity
from markforge.calc.engine.verify import double_check
from tests.calc.test_behaviour import sheet

BEAM = ["F:12.5'kN", "L:4'm", "M:F*L/4", "M=", "b:300'mm", "h:500'mm", "I:b*h^3/12", "I=",
        "q:5'kN/'m", "q=", "E:200'GPa", "E=", "x:2.00025", "x=", "y:x*3-1", "y=", "z:sqrt(16'm^2)", "z="]


def test_correct_sheet_agrees():
    ws, _ = sheet(*BEAM)
    rep = double_check(ws)
    assert rep.ok and rep.checked >= 12, rep.summary()


def _find(ws, text):
    return next(r for r in ws.ordered() if r.editor.root.text() == text)


def test_wrong_value_is_caught():
    ws, _ = sheet(*BEAM)
    r = _find(ws, "M=")
    r.value = Quantity(r.value.value * 1.001, r.value.dims)  # a 0.1% error
    rep = double_check(ws)
    assert [x[0] for x in rep.mismatches] == [r]


def test_wrong_unit_is_caught():
    ws, _ = sheet(*BEAM)
    r = _find(ws, "q=")
    r.value = Quantity(r.value.value, (0, 1, -2, 0, 0, 0, 0, 0, 0, 0, 0))  # kg/s^2 -> lost a metre?
    r.value = Quantity(r.value.value, (1, 1, -2, 0, 0, 0, 0, 0, 0, 0, 0))  # N instead of N/m
    assert not double_check(ws).ok


def test_wrong_display_is_caught():
    ws, _ = sheet(*BEAM)
    r = _find(ws, "M=")
    d = display_value(r.value, ws.format)
    d.value = DNum(format_real(12.4, ws.format))  # shows 12.4 kN m instead of 12.5
    r.display = d
    rep = double_check(ws)
    assert rep.mismatches and rep.mismatches[0][1] == "display"


def test_stale_definition_is_caught():
    # a definition whose stored value was not updated (what a missed
    # dependency in the incremental recalculation would leave behind)
    ws, _ = sheet(*BEAM)
    r = _find(ws, "y≔x*3-1")
    r.defined_vars["y"] = Quantity(99.0)
    assert not double_check(ws).ok


EXAMPLES = Path(__file__).resolve().parents[2] / "SMath Studio" / "examples"


@pytest.mark.skipif(not EXAMPLES.exists(), reason="SMath Studio examples not present")
@pytest.mark.parametrize("path", sorted(glob.glob(str(EXAMPLES / "*.sm"))), ids=lambda p: Path(p).name)
def test_smath_examples_double_check(path):
    from tests.calc.smfile import load_sm

    rep = double_check(load_sm(path))
    assert rep.ok, [(r.editor.root.text(), what, exp, got) for r, what, exp, got in rep.mismatches]
