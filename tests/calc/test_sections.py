"""Calculation sections (the user's request, 2026-10-11), at the worksheet: a
section break starts the calculation afresh; what a global region defines
is still read by every later section."""
from __future__ import annotations

from calcforge.calc.worksheet import Worksheet
from tests.calc.test_block_scope import region, shown


def two_sections():
    ws = Worksheet()
    first = [region(ws, 0, "a:2"), region(ws, 20, "b:30"), region(ws, 40, "a=")]
    second = [region(ws, 1000, "a="), region(ws, 1020, "b="), region(ws, 1040, "a:7"),
              region(ws, 1060, "a=")]
    ws.index.starts = [(1000,)]
    return ws, first, second


def test_a_section_does_not_see_the_one_before():
    ws, first, second = two_sections()
    ws.calculate()
    assert shown(first[2]) == "2"
    assert second[0].error is not None, "a was defined in the section before"
    assert second[1].error is not None, "and so was b"
    assert shown(second[3]) == "7", "a section defines its own"


def test_a_global_region_is_read_by_every_later_section():
    ws, first, second = two_sections()
    first[0].is_global = True
    ws.calculate()
    assert shown(second[0]) == "2"
    assert second[1].error is not None, "only what the global region defines"
    assert shown(second[3]) == "7", "and a later section can still redefine it"
    # a third section reads it too
    third = region(ws, 2000, "a=")
    ws.index.starts = [(1000,), (2000,)]
    ws.calculate()
    assert shown(third) == "2"


def test_making_a_region_global_updates_the_sections_after_it():
    ws, first, second = two_sections()
    ws.calculate()
    assert second[0].error is not None
    first[0].is_global = True
    ws.update_after_edit(first[0])
    assert shown(second[0]) == "2"
    first[0].is_global = False
    ws.update_after_edit(first[0])
    assert second[0].error is not None


def test_no_breaks_is_one_document():
    ws, first, second = two_sections()
    ws.index.starts = []
    ws.calculate()
    assert shown(second[0]) == "2" and shown(second[1]) == "30"
