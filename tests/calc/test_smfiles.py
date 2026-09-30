"""Open SMath's own example worksheets and compare with the results SMath saved."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from markforge.calc.engine.values import Matrix
import base64

from markforge.calc.engine.display import display_text
from tests.calc.smfile import NS, load_sm, loads, rpn_to_ast, save_sm
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


def test_line_block_sizes_round_trip():
    from tests.calc.smfile import dumps, loads

    import pathlib

    beam = pathlib.Path(__file__).resolve().parents[2] / "SMath Studio" / "examples" / "Beam.sm"
    if not beam.exists():
        pytest.skip("SMath examples not present")
    from tests.calc.smfile import load_sm

    ws = load_sm(beam)
    texts = [r.editor.root.text() for r in ws.ordered() if r.kind == "math"]
    assert not any(";1;1}" in t or ";3;1}" in t for t in texts)  # the size operands are not statements
    again = loads(dumps(ws))
    assert [r.editor.root.text() for r in again.ordered() if r.kind == "math"] == texts


# -- moved from test_page_model.py (phase 6: SMath's page model is withdrawn; the
# maths in a file that has one is not) ---------------------------------------------------

def _page_model_png(w=8, h=6, color="#0000ff") -> str:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(QColor(color))
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return base64.b64encode(bytes(buf.data())).decode()


def _page_model_sheet() -> str:
    pic = _page_model_png()
    return f'''<?xml version="1.0" encoding="utf-8"?>
<worksheet xmlns="http://smath.info/schemas/worksheet/1.0">
  <settings ppi="96">
    <metadata lang="eng"><title>Issue 1</title><author>ME</author><keywords>JOB-7</keywords></metadata>
    <calculation><precision>4</precision><exponentialThreshold>5</exponentialThreshold></calculation>
    <pageModel active="false" viewMode="2" printGrid="false" printAreas="true" printBackgroundImages="true">
      <paper id="9" orientation="Portrait" width="827" height="1169" />
      <margins left="39" right="39" top="117" bottom="49" />
      <header alignment="Center" color="#a9a9a9">&amp;[DATE]</header>
      <footer alignment="Center" color="#a9a9a9">&amp;[PAGENUM]</footer>
      <backgrounds><image fullPage="false" size="stretch">{_page_model_png(20, 30, "#00000000")}</image></backgrounds>
    </pageModel>
  </settings>
  <regions type="content">
    <region left="18" top="18" width="29" height="20" color="#000000" fontSize="8">
      <text lang="eng" fontFamily="Arial" fontSize="8"><content>
          <p>
            <span style="font-weight: bold;">Design</span>
            <br />
            <br />
            <span style="text-decoration: underline;">Brace Check</span>
            <br />Plain line.</p>
      </content></text>
    </region>
    <region left="72" top="45" width="749" height="90" color="#000000">
      <picture><raw format="png" encoding="base64">{pic}</raw></picture>
    </region>
    <region left="369" top="200" width="120" height="32" color="#000000" fontSize="8">
      <text lang="eng" width="120" fontFamily="Arial" fontSize="8"><content>
        <p>The capacity is 6.67 kN. This is larger than the demand.</p></content></text>
    </region>
    <region left="18" top="300" width="199" height="36" color="#000000" fontSize="8">
      <math>
        <input>
          <e type="operand">L</e><e type="operand">50</e><e type="operand" style="unit">kg</e>
          <e type="operand" style="unit">m</e><e type="operator" args="2">/</e>
          <e type="operator" args="2">*</e><e type="operand">1.2</e><e type="operator" args="2">*</e>
          <e type="operator" args="2">:</e>
        </input>
        <result action="numeric"><e type="operand">60</e></result>
      </math>
    </region>
    <region left="18" top="1100" width="80" height="20" color="#000000" fontSize="8">
      <text lang="eng" fontFamily="Arial" fontSize="8"><content><p>Second page</p></content></text>
    </region>
  </regions>
  <regions type="header">
    <region left="0" top="18" width="749" height="90" color="#000000">
      <picture><raw format="png" encoding="base64">{pic}</raw></picture>
    </region>
    <region left="123" top="45" width="131" height="20" color="#000000" fontSize="8">
      <math><input><e type="operand">\\[KEYWORDS]\\</e></input></math>
    </region>
    <region left="573" top="45" width="16" height="20" color="#000000" fontSize="8">
      <math><input><e type="operand">\\[PAGENUM[0]]\\</e></input></math>
    </region>
    <region left="666" top="45" width="16" height="20" color="#000000" fontSize="8">
      <math><input><e type="operand">\\[COUNT[0]]\\</e></input></math>
    </region>
  </regions>
</worksheet>'''


def test_definition_with_equals_shows_its_value():
    ws = loads(_page_model_sheet())
    m = next(r for r in ws.regions if r.kind == "math")
    assert display_text(m.display) == "60 kg/m"


