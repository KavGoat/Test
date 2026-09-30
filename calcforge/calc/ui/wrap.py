"""Breaking an equation that is too wide for its page onto more lines.

SMath lets a long equation run off the edge of the sheet; CalcForge's pages
are fixed, so an equation that would not fit is broken (the user's answer to
the "too wide" question): before an operator at the top level of the
expression — + − · = := and the comparisons, never a sign in front of a
number — with every later line indented under the start of the right-hand
side, the way an engineer writes a long line out by hand. The result follows
the last line.

It is display only. The equation is the same tree and calculates the same;
while it is being typed into it is shown on one line, so the cursor and the
editor work exactly as WebSMath's do. Where no break makes it fit, it is
left as it is and marked too wide.
"""
from __future__ import annotations

from typing import Optional

from ..engine.model import Box
from ..ui.layout import LBox, LErrorSpan

BREAK_BEFORE = {"+", "-", "*", "=", "≔", "<", ">", "≤", "≥", "≠", "≡", "∧", "∨", "⊕", "×"}
DEFINES = {"≔", "="}
LINE_GAP = 4.0          # px between broken lines


def _break_points(items, slots) -> list:
    """(slot x, is a definition sign) for every place the top-level row may break."""
    points = []
    for i, it in enumerate(items):
        if i == 0 or not isinstance(it, str) or it not in BREAK_BEFORE:
            continue
        before = items[i - 1]
        if it in "+-" and isinstance(before, str) and before in BREAK_BEFORE:
            continue                                   # a sign, not an operation
        # the definition or evaluation sign is where the indent is measured
        # from, never a break: the name stays with what it is given
        points.append((slots[i], it in DEFINES, None if it in DEFINES else _RANK.get(it, 1)))
    return points


# Where a line is best broken: before the loosest-binding operator that fits
# — a comparison, then + and −, and only then inside a product.
_RANK = {"=": 0, "≔": 0, "<": 0, ">": 0, "≤": 0, "≥": 0, "≠": 0, "≡": 0,
         "+": 1, "-": 1, "∨": 1, "⊕": 1, "*": 2, "×": 2, "∧": 2}


def wrap(whole: LBox, row, max_width: float, pad_x: float) -> Optional[LBox]:
    """Break *whole* (the region's laid-out input and result) to *max_width*.

    Returns the rebuilt box, or None when it already fits, cannot be broken,
    or still would not fit.
    """
    if max_width <= 0 or whole.w + 2 * pad_x <= max_width or not whole.children:
        return None
    root = whole.children[0]
    slots = getattr(root, "slots", None)
    if slots is None or any(isinstance(c, LErrorSpan) for c in root.children):
        return None
    points = _break_points(row.items, slots)
    if not any(rank is not None for _x, _d, rank in points):
        return None
    # indent later lines under the right-hand side: just after the first
    # definition or evaluation sign, else under the first operand
    indent = 0.0
    for x, defines, _rank in points:
        if defines:
            nxt = [c.x for c in root.children if c.x > x + 1e-6]
            indent = min(nxt) if nxt else x
            break
    budget = max_width - 2 * pad_x
    # greedy: break before the last operator that still lets the line fit
    lines = [0.0]                                      # x in the unbroken row where each line starts
    candidates = sorted((x, rank) for x, _d, rank in points if rank is not None)
    line_start, shift = 0.0, 0.0
    for c in root.children:
        right = c.x + c.w
        if right - line_start + shift <= budget:
            continue
        usable = [(x, rank) for x, rank in candidates if line_start < x <= c.x + 1e-6]
        if not usable:
            continue
        best = min(rank for _x, rank in usable)
        line_start = [x for x, rank in usable if rank == best][-1]
        shift = indent
        lines.append(line_start)
    if len(lines) == 1:
        return None
    line_h = root.asc + root.desc + LINE_GAP
    # work the new places out first; nothing is moved unless it all fits
    placed = []
    widest = 0.0
    for c in root.children:
        k = max(i for i, start in enumerate(lines) if c.x + 1e-6 >= start)
        x = c.x + (indent if k else 0.0) - lines[k]
        placed.append((c, x, c.y + k * line_h, k))
        widest = max(widest, x + c.w)
    last = len(lines) - 1
    end = max((x + c.w for c, x, _y, k in placed if k == last), default=0.0)
    after = []
    gap = None
    for part in whole.children[1:]:
        gap = (part.x - root.w) if gap is None else 3.0
        after.append((part, end + gap, last * line_h))
        end = end + gap + part.w
    total = max([widest] + [x + p.w for p, x, _y in after])
    if total + 2 * pad_x > max_width + 1e-6:
        return None
    new_root = LBox(asc=root.asc, x=root.x, y=root.y)
    for c, x, y, _k in placed:
        c.x, c.y = x, y
        new_root.children.append(c)
    new_root.w = widest
    new_root.desc = root.desc + last * line_h
    parts = [new_root]
    for part, x, y in after:
        part.x, part.y = x, y
        parts.append(part)
    out = LBox(children=parts, x=whole.x, y=whole.y)
    out.w = total
    out.asc = whole.asc
    out.desc = max([new_root.desc] + [p.y + p.desc for p in parts[1:]])
    return out
