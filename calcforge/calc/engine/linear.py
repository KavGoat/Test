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


def parse_text(text: str):
    """Build a Row from ordinary linear maths text, with brackets closing
    as written (unlike typing, where ")" is ignored): "stack(augment(1,2),
    augment(3,4))", "x^(1/2)", "f(x):=x^3".  "^" takes the next number, name
    or bracket as its exponent."""
    from .model import Index, Paren, Pow, Row

    text = text.replace(":=", "≔").replace(":", "≔")
    pos = 0

    def atom_end(i):
        # a number or name (with ' and subscript dots) starting at i
        j = i
        while j < len(text) and (text[j].isalnum() or text[j] in "._'"):
            j += 1
        return j

    def row(stop: str) -> "Row":
        nonlocal pos
        r = Row()
        while pos < len(text):
            ch = text[pos]
            if ch == stop:
                pos += 1
                return r
            if ch == " ":
                pos += 1
                continue
            if ch == "(":
                pos += 1
                box = Paren(row(")"))
                _attach(r, box)
                continue
            if ch == "[":
                pos += 1
                _attach(r, Index(row("]")))
                continue
            if ch == "^":
                pos += 1
                if pos < len(text) and text[pos] == "(":
                    pos += 1
                    inner = row(")")
                else:
                    j = atom_end(pos)
                    if j == pos and pos < len(text) and text[pos] == "-":
                        j = atom_end(pos + 1)
                    inner = Row(list(text[pos:j]))
                    pos = j
                _attach(r, Pow(inner))
                continue
            r.items.append(ch)
            pos += 1
        return r

    def _attach(r, box):
        box.parent_row = r
        for c in box.rows:
            c.parent = box
        r.items.append(box)

    return row("\0")
