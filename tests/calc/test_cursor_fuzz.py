"""Arrow keys: from the start of any equation Right walks through it to the
end without getting stuck or looping, Left walks back to the start, and
neither changes the equation."""
from __future__ import annotations

import random

import pytest

from markforge.calc.editor import MathEditor
from markforge.calc.engine.model import Box
KEYS = list("0123456789xyab+-*/^(),'") + ["RIGHT","RIGHT","'kN","sqrt(","mat(","if(","sin("]
def state(ed):
    return (id(ed.row), ed.pos, ed.node and (id(ed.node[0]), ed.node[1], ed.node[2]))


def _walk(ed, direction, target):
    seen, steps = set(), 0
    while steps < 400:
        if target(ed):
            return True
        st = state(ed)
        if st in seen:
            return False
        seen.add(st)
        ed.key(direction)
        steps += 1
    return False


@pytest.mark.parametrize("block", range(10))
def test_arrows_walk_every_equation(block):
    for seed in range(block * 200, block * 200 + 200):
        rng = random.Random(seed)
        ed = MathEditor()
        for _ in range(rng.randint(3, 25)):
            k = rng.choice(KEYS)
            (ed.type(k) if len(k) > 1 and k != "RIGHT" else ed.key(k))
        if ed.kind != "math" or ed.root.is_empty():
            continue
        text = ed.root.text()
        ed.set_cursor(ed.root, 0)
        ed.node = None
        assert _walk(ed, "RIGHT", lambda e: e.row is e.root and e.pos == len(e.root.items) and e.node is None), seed
        ed.set_cursor(ed.root, len(ed.root.items))
        ed.node = None
        assert _walk(ed, "LEFT", lambda e: e.row is e.root and e.pos == 0), seed
        assert ed.root.text() == text, seed
