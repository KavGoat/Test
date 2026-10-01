"""CalcForge types and draws equations exactly as WebSMath does.

The reference was made by running WebSMath's own window (branch
claude/zealous-clarke-8yiu03 @ 8b340fa, the commit CalcForge's drawing code
came from) through the keystrokes in websmath_scenarios.py, and keeping, at
every ("snap", ...) step, the equation's drawing (4x) and what it said: its
text, unit box, result, error, the caret's place and the suggestion list
(tests/calc/data/websmath_reference). Here the same keystrokes go into the
CalcForge window and both must match — pixel for pixel, caret and colours
included.

One difference is deliberate and asserted as such: a name that is also a
unit (a is the are) no longer blocks the next key (the user, 2026-10-01: "I
couldn't type = at all"), so `a*a=` after `a:5` is 25 here where WebSMath
made `aa≔`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent, QPainter
from PySide6.QtWidgets import QApplication

from calcforge.calc.docsheet import PT_PER_PX, sheet_for
from calcforge.calc.engine.display import display_text
from tests.calc.websmath_scenarios import SCENARIOS

REFERENCE = Path(__file__).parent / "data" / "websmath_reference"
FACTS = json.loads((REFERENCE / "facts.json").read_text(encoding="utf-8"))
KEYS = {"Return": Qt.Key_Return, "Right": Qt.Key_Right, "Left": Qt.Key_Left,
        "Backspace": Qt.Key_Backspace}
SCALE = 4.0
DELIBERATE = {
    "matrix_eval.left": {"text": "a*a=", "shown": "25", "error": None},
}


def _render(paint, rect: QRectF) -> QImage:
    image = QImage(int(rect.width() * SCALE) + 2, int(rect.height() * SCALE) + 2,
                   QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.scale(SCALE, SCALE)
    painter.translate(-rect.topLeft())
    paint(painter)
    painter.end()
    return image


def _facts(item, suggestions) -> dict:
    r = item.region
    ed = r.editor
    return {
        "text": ed.root.text(), "unit": ed.unit.text(),
        "shown": display_text(r.display) if r.display is not None else None,
        "error": r.error.message if r.error is not None else None,
        "pending": bool(r.pending), "cursor_pos": ed.pos,
        "cursor_in_root": ed.row is ed.root, "in_unit": bool(ed.in_unit),
        "suggestions": [suggestions.item(i).text() for i in range(min(suggestions.count(), 6))]
                       if suggestions.isVisible() else [],
    }


def _run(window, steps):
    window.show()
    window.toggle_calc_mode(True)
    view, calc = window.view, window.view.calc
    frame = window.document.pages[0].frame
    seen = {}
    for step in steps:
        if isinstance(step, str):
            for ch in step:
                QApplication.sendEvent(view, QKeyEvent(QKeyEvent.KeyPress, 0, Qt.NoModifier, ch))
        elif step[0] == "at":
            calc.leave()
            view.scene().clearSelection()
            calc.place_cross(frame, QPointF(step[1] * PT_PER_PX, step[2] * PT_PER_PX))
        elif step[0] == "key":
            QApplication.sendEvent(view, QKeyEvent(QKeyEvent.KeyPress, KEYS[step[1]],
                                                   Qt.NoModifier, ""))
        elif step[0] == "snap":
            QApplication.instance().processEvents()
            items = getattr(sheet_for(window.document), "items", {})
            item = calc.item or max(items.values(), key=lambda i: i.region.id)
            drawing = item._view
            seen[step[1]] = (_facts(item, calc.suggestions),
                             _render(lambda p: drawing.paint(p, None), drawing.boundingRect()))
    return seen


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_same_keystrokes_make_the_same_equation_as_websmath(window, name):
    for snap, (facts, image) in _run(window, SCENARIOS[name]).items():
        key = f"{name}.{snap}"
        expected = dict(FACTS[key])
        if key in DELIBERATE:
            expected.update(DELIBERATE[key])
            for field, value in DELIBERATE[key].items():
                assert facts[field] == value, (key, field)
            continue                             # the drawing differs with the text
        assert facts == expected, key
        reference = QImage(str(REFERENCE / f"{key}.png"))
        assert image.size() == reference.size(), key
        assert image == reference.convertToFormat(image.format()), \
            f"{key}: not drawn as WebSMath draws it"
