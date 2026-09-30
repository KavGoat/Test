"""Incremental recalculation must always agree with a full recalculation."""
from __future__ import annotations

import random
import time

from calcforge.calc.engine.display import display_text
from calcforge.calc.worksheet import Worksheet


def shown(ws):
    return {r.id: (display_text(r.display) if r.display else None, r.error.message if r.error else None)
            for r in ws.regions}


def build(lines):
    ws = Worksheet()
    regs = []
    for k, line in enumerate(lines):
        r = ws.add_region(18, 9 + 36 * k)
        for key in (line if isinstance(line, list) else list(line)):
            r.editor.key(key)
        ws.update_after_edit(r)
        regs.append(r)
    return ws, regs


def test_changing_a_definition_updates_dependants_only_when_left():
    ws, (a, b, c, d) = build(["x:2", "y:x*3", "y=", "z:5"])
    assert display_text(c.display) == "6"
    a.editor.key("BACK")
    a.editor.key("4")
    ws.calculate_region(a)  # still editing
    assert display_text(c.display) == "6"
    ws.take_changed()
    ws.update_after_edit(a)  # left the region
    assert display_text(c.display) == "12"
    assert c.id in ws.take_changed() and d.id not in ws.changed


def test_function_body_dependency():
    ws, regs = build(["k:2", ["f", "(", "t", "RIGHT", ":", "k", "*", "t"], "f(5=", "k2:1"])
    assert display_text(regs[2].display) == "10"
    regs[0].editor.key("BACK")
    regs[0].editor.key("3")
    ws.update_after_edit(regs[0])
    assert display_text(regs[2].display) == "15"


def test_random_edits_match_full_recalculation():
    rnd = random.Random(7)
    names = ["a", "b", "c", "d"]
    lines = []
    for k in range(40):
        n = rnd.choice(names)
        if rnd.random() < 0.4:
            lines.append(n + "=")
        else:
            m = rnd.choice(names)
            lines.append(f"{n}:{m}+{k}" if rnd.random() < 0.6 else f"{n}:{k}")
    ws, regs = build(lines)
    for _ in range(60):
        r = rnd.choice(regs)
        if r.editor.root.items and r.editor.root.items[-1] != "=":
            r.editor.set_cursor(r.editor.root, len(r.editor.root))
            r.editor.key(str(rnd.randint(0, 9)))
        if rnd.random() < 0.2:
            r.y = rnd.randint(0, 40) * 36 + 9  # move it
        ws.update_after_edit(r)
        incremental = shown(ws)
        ws.calculate()
        assert shown(ws) == incremental


def test_thousands_of_variables_stay_fast():
    n = 3000
    ws = Worksheet()
    t0 = time.perf_counter()
    regs = []
    for i in range(n):
        r = ws.add_region(18, 9 + 36 * i)
        r.editor.type(f"v{i}:{i}" if i % 10 else (f"v{i - 1}=" if i else "v0:0"))
        ws.update_after_edit(r)
        regs.append(r)
    build_time = time.perf_counter() - t0
    t0 = time.perf_counter()
    last = regs[-3]
    for _ in range(50):
        last.editor.key("1")
        ws.calculate_region(last)
    keystroke = (time.perf_counter() - t0) / 50
    t0 = time.perf_counter()
    ws.update_after_edit(regs[5])
    leave_top = time.perf_counter() - t0
    assert build_time < 20
    assert keystroke < 0.01
    assert leave_top < 1.0
