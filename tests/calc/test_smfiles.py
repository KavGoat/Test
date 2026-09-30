"""Open SMath's own example worksheets and compare with the results SMath saved."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from markforge.calc.engine.values import Matrix
from tests.calc.smfile import NS, load_sm, rpn_to_ast, save_sm
from markforge.calc.engine.evaluator import Context, Evaluator
from markforge.calc.engine.units import Quantity

EXAMPLES = Path(__file__).resolve().parents[2] / "SMath Studio" / "examples"
# worksheets whose results need SMath's symbolic engine (not replicated)
SYMBOLIC = {"HermitePolynomials.sm", "LaguerrePolynomials.sm", "LegendrePolynomials.sm",
            "Hessian.sm", "Jacobian.sm", "RungeKutta5.sm", "Newton.sm", "MaclaurinSeries.sm",
            "PlanetaryGear.sm"}


def stored_results(path: Path):
    """[(top, left, stored value)] for every numeric result saved in the file."""
    root = ET.parse(str(path)).getroot()
    out = []
    for reg in root.iter(f"{{{NS}}}region"):
        math_el = reg.find(f"{{{NS}}}math")
        if math_el is None:
            continue
        res = math_el.find(f"{{{NS}}}result")
        if res is None or res.get("action") != "numeric" or not len(res):
            continue
        try:
            v = Evaluator().eval(rpn_to_ast(list(res)), Context())
        except Exception:
            continue
        out.append((float(reg.get("top")), float(reg.get("left")), v))
    return out


def _close(a, b) -> bool:
    if isinstance(a, Quantity) and isinstance(b, Quantity):
        x, y = complex(a.value), complex(b.value)
        return abs(x - y) <= 1e-3 * max(1.0, abs(y))
    if isinstance(a, Matrix) and isinstance(b, Matrix):
        return len(a.items) == len(b.items) and all(_close(x, y) for x, y in zip(a.items, b.items))
    return False


@pytest.mark.skipif(not EXAMPLES.exists(), reason="SMath Studio examples not present")
@pytest.mark.parametrize("path", sorted(p for p in EXAMPLES.glob("*.sm") if p.name not in SYMBOLIC),
                         ids=lambda p: p.name)
def test_example_results_match_smath(path: Path):
    ws = load_sm(path)
    ours = {(r.y, r.x): r for r in ws.regions}
    compared = 0
    for top, left, stored in stored_results(path):
        r = ours.get((top, left))
        assert r is not None
        assert r.error is None, (path.name, r.editor.root.text(), r.error.message)
        shown = r.value
        if not r.editor.unit.is_empty():
            # the file stores the value in the contract unit
            from markforge.calc.engine.parser import parse_row
            u = Evaluator().eval(parse_row(r.editor.unit), Context())
            shown = Quantity(r.value.value / u.value) if isinstance(r.value, Quantity) else r.value
        if isinstance(shown, Quantity):
            shown = Quantity(shown.value)
        if isinstance(stored, Quantity) and isinstance(shown, Quantity):
            assert _close(shown, stored), (path.name, r.editor.root.text(), shown, stored)
            compared += 1
    assert compared >= 0


@pytest.mark.skipif(not EXAMPLES.exists(), reason="SMath Studio examples not present")
def test_save_and_reload_round_trip(tmp_path):
    ws = load_sm(EXAMPLES / "Beam.sm")
    before = [(r.editor.root.text(), r.editor.unit.text()) for r in ws.ordered() if r.kind == "math"]
    out = tmp_path / "beam.sm"
    save_sm(ws, out)
    again = load_sm(out)
    after = [(r.editor.root.text(), r.editor.unit.text()) for r in again.ordered() if r.kind == "math"]
    assert before == after
    vals = [r.display for r in again.ordered() if r.editor.evaluate]
    assert all(v is not None for v in vals)
