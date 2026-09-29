"""Build a Row by *typing* text into the editor, exactly as a user would.

Used by str2num() and the tests; it means linear text is read with SMath's
keystroke semantics (``1/7*1000`` is 1 over 7·1000).
"""
from __future__ import annotations


def parse_linear(text: str):
    from ..editor import MathEditor

    ed = MathEditor()
    ed.type(text)
    return ed.root
