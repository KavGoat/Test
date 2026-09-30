"""Self-contained calculation blocks (CalcForge decision 10), at the
worksheet: a block reads everything defined above it, and what it defines
stays inside it."""
from __future__ import annotations

from markforge.calc.editor import MathEditor
from markforge.calc.engine.display import display_text
from markforge.calc.worksheet import Worksheet


def region(ws, y, text, x=0):
    """A region typed in. A trailing "=" is typed as an evaluation, whether or
    not the name is known yet (SMath's editor reads "a=" on an unknown a as
    a definition)."""
    editor = MathEditor()
    r = ws.add_region(x, y, editor)
    evaluate = text.endswith("=") and ":" not in text
    for ch in (text[:-1] if evaluate else text):
        editor.key(ch)
    if evaluate:
        known, editor.is_defined = editor.is_defined, (lambda *_a, **_k: True)
        editor.key("=")
        editor.is_defined = known
    return r


def shown(r):
    return display_text(r.display) if r.display is not None else None


def a_sheet():
    ws = Worksheet()
    outside = region(ws, 0, "a:1")
    inner = [region(ws, 100, "b:a+1"), region(ws, 120, "a:5"), region(ws, 140, "a+b=")]
    after = [region(ws, 300, "a="), region(ws, 320, "b=")]
    return ws, outside, inner, after


def test_without_a_self_contained_block_everything_is_shared():
    ws, outside, inner, after = a_sheet()
    ws.calculate()
    assert shown(inner[2]) == "7"
    assert shown(after[0]) == "5" and shown(after[1]) == "2"


def test_a_self_contained_block_reads_above_and_keeps_its_own_names():
    ws, outside, inner, after = a_sheet()
    ws.set_scopes({r.id: "block-1" for r in inner})
    ws.calculate()
    assert shown(inner[2]) == "7", "inside: a from inside (5), b from a above (1+1)"
    assert shown(after[0]) == "1", "outside, a is still the a defined above"
    assert after[1].error is not None, "b was defined inside the block only"


def test_editing_above_the_block_updates_inside_it():
    ws, outside, inner, after = a_sheet()
    ws.set_scopes({r.id: "block-1" for r in inner})
    ws.calculate()
    outside.editor.key("0")                     # a:10
    ws.update_after_edit(outside)
    assert shown(inner[2]) == "16", "b = 10 + 1, a inside still 5"
    assert shown(after[0]) == "10"


def test_two_blocks_do_not_see_each_other():
    ws = Worksheet()
    first = [region(ws, 0, "k1:3"), region(ws, 20, "k1=")]
    second = [region(ws, 100, "k1=")]
    ws.set_scopes({**{r.id: "one" for r in first}, **{r.id: "two" for r in second}})
    ws.calculate()
    assert shown(first[1]) == "3"
    assert second[0].error is not None


def test_moving_a_region_out_of_a_block_recalculates():
    ws, outside, inner, after = a_sheet()
    ws.set_scopes({r.id: "block-1" for r in inner})
    ws.calculate()
    assert after[1].error is not None
    ws.set_scopes({r.id: "block-1" for r in inner[1:]})      # b:=a+1 is outside now
    ws.update_after_edit(inner[0])
    assert shown(after[1]) == "2"
