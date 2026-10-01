"""CalcForge types and draws equations exactly as WebSMath does.

The reference was made by running WebSMath's own window (branch
claude/zealous-clarke-8yiu03 @ 8b340fa, the commit CalcForge's drawing code
came from) through the keystrokes in websmath_scenarios.py, and keeping, at
every ("snap", ...) step, the equation's drawing (4x) and what it said: its
text, unit box, result, error, the caret's place and the suggestion list
(tests/calc/data/websmath_reference). Here the same keystrokes go into the
CalcForge window and both must match — pixel for pixel, caret and colours
included.

Two differences are deliberate and asserted as such. The caret on an empty
slot (the result's unit box) stands clear of the placeholder square, which
WebSMath's caret cut through. And a name that is also a
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
        "Backspace": Qt.Key_Backspace, "Home": Qt.Key_Home, "End": Qt.Key_End,
        "Escape": Qt.Key_Escape, "Up": Qt.Key_Up, "Down": Qt.Key_Down, "Tab": Qt.Key_Tab,
        "Delete": Qt.Key_Delete}
SCALE = 4.0
DELIBERATE = {
    "matrix_eval.left": {"text": "a*a=", "shown": "25", "error": None},
}
# Drawn differently on purpose (same facts): the caret on an empty slot
# stands clear of the placeholder square instead of cutting through it
# (the user, 2026-10-01: "a weird white box round the second black box").
DRAWN_DIFFERENTLY = {"result_unit.in_unit_box", "reopen_name.b", "reopen_name.c",
                     "reopen_name.d", "reopen_end.b"}


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


def _click(view, scene_point) -> None:
    """A real click, through the view, as the user makes one."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    local = QPointF(view.mapFromScene(scene_point))
    where = QPointF(view.viewport().mapToGlobal(local.toPoint()))
    for kind, buttons in ((QEvent.MouseButtonPress, Qt.LeftButton),
                          (QEvent.MouseButtonRelease, Qt.NoButton)):
        QApplication.sendEvent(view.viewport(), QMouseEvent(kind, local, where, Qt.LeftButton,
                                                            buttons, Qt.NoModifier))


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
        elif step[0] == "click":
            made = sorted(sheet_for(window.document).items.values(), key=lambda i: i.region.id)
            _click(view, made[step[1]].mapToScene(QPointF(step[2], step[3]) * PT_PER_PX))
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
        if key in DRAWN_DIFFERENTLY:
            continue
        reference = QImage(str(REFERENCE / f"{key}.png"))
        assert image.size() == reference.size(), key
        assert image == reference.convertToFormat(image.format()), \
            f"{key}: not drawn as WebSMath draws it"


def test_the_caret_on_an_empty_slot_stands_clear_of_its_square(window):
    """The underline runs under the square and the bar is just past its
    right edge — not through it (WebSMath's bar was 7 px in, cutting the
    5 px square that starts 3 px in)."""
    from calcforge.calc.ui.layout import Layouter
    drawn = []

    class Spy:
        def __init__(self, painter):
            self.p = painter

        def __getattr__(self, name):
            return getattr(self.p, name)

        def drawLine(self, a, b):
            drawn.append((a, b))

    _run(window, [("at", 18, 18), "x:2'kN", ("key", "Return"), ("at", 18, 72), "x=",
                  ("key", "Right")])
    item = window.view.calc.item
    view = item._view
    info = view._row_info(item.editor.row)
    square = Layouter(view.style).placeholder()
    left, width = info.x + square.box[0], info.x + square.box[0] + square.box[1]
    image = QImage(200, 100, QImage.Format_ARGB32)
    painter = QPainter(image)
    view._paint_cursor(Spy(painter))
    painter.end()
    under = [(a, b) for a, b in drawn if a.y() == b.y()][0]
    bar = [(a, b) for a, b in drawn if a.x() == b.x()][0]
    assert abs(under[0].x() - left) < 0.01, "the underline starts at the square"
    assert width < bar[0].x() < width + 2.5, "the bar just past the square, not through it"
    assert bar[0].x() < view.frame_rect().width() - 1, "and inside the equation's frame"

