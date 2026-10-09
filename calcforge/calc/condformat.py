"""Conditional formatting for equations: their look follows their result.

The user, 2026-10-09: "add a conditional formatting to smath equation …
based on the final number, like for dcr … more than 1 is red, less than 1
is green". Their answers:

* a rule changes the equation's font size and background — WebSMath's
  drawing (kept byte for byte) draws only those two on maths;
* it restyles the whole equation;
* rules are set per equation, kept as named presets, and also for the whole
  document by variable name (DCR* → the "DCR" preset);
* only results without units are compared (DCR, ratios); a result with
  units never matches.

A rule: {"op": ">", "a": 1.0, "b": None, "size": None, "bg": "#ffc9c9"};
op is one of > >= < <= = <> between outside. Every rule that matches is
applied, an earlier one winning where two set the same thing.

Which rules an equation uses: its own; else its preset; else the first
document rule whose name pattern matches what it defines or shows.

The equation's own size and background are never changed: the rule's look
is put on only while it is laid out and drawn (``looking``), so what the
record keeps, and what a menu sets, is always the equation's own.
"""
from __future__ import annotations

import fnmatch
from contextlib import contextmanager
from typing import Optional

OPS = [(">", "greater than"), (">=", "greater than or equal to"), ("<", "less than"),
       ("<=", "less than or equal to"), ("=", "equal to"), ("<>", "not equal to"),
       ("between", "between"), ("outside", "not between")]

#: what the "DCR" button in the dialogs fills in
DCR_EXAMPLE = [{"op": ">", "a": 1.0, "b": None, "size": None, "bg": "#ffc9c9"},
               {"op": "<=", "a": 1.0, "b": None, "size": None, "bg": "#d3f9d8"}]


def matches(rule: dict, x: float) -> bool:
    op, a = rule.get("op", ">"), float(rule.get("a") or 0.0)
    b = rule.get("b")
    b = float(b) if b is not None else a
    lo, hi = min(a, b), max(a, b)
    eps = 1e-12 * max(1.0, abs(a))
    return {">": x > a, ">=": x >= a - eps, "<": x < a, "<=": x <= a + eps,
            "=": abs(x - a) <= eps, "<>": abs(x - a) > eps,
            "between": lo - eps <= x <= hi + eps, "outside": x < lo or x > hi}.get(op, False)


def describe(rule: dict) -> str:
    op = dict(OPS).get(rule.get("op"), rule.get("op"))
    a = f"{float(rule.get('a') or 0):g}"
    cond = f"{op} {a} and {float(rule.get('b') or 0):g}" if rule.get("op") in ("between", "outside") \
        else f"{op} {a}"
    look = []
    if rule.get("bg"):
        look.append(f"background {rule['bg']}")
    if rule.get("size"):
        look.append(f"{float(rule['size']):g} pt")
    return f"Result {cond}: " + (", ".join(look) or "no change")


def result_number(region) -> Optional[float]:
    """The number the equation's rules look at: what it shows (x=), or what
    it defines (DCR:=…); None when there is none, it isn't a plain real
    number, or it has units."""
    from .engine.units import Quantity

    value = region.value if getattr(region, "editor", None) is not None and region.editor.evaluate else None
    if value is None and len(region.defined_vars or {}) == 1:
        value = next(iter(region.defined_vars.values()))
    if region.error is not None or not isinstance(value, Quantity):
        return None
    if any(value.dims):
        return None                       # results with units never match (the user's choice)
    v = value.value
    if isinstance(v, complex):
        if v.imag:
            return None
        v = v.real
    return float(v)


def result_name(region) -> str:
    """The name a document rule matches: the variable defined (DCR:=…), or
    the one shown (DCR=)."""
    if len(region.defined_vars or {}) == 1:
        return next(iter(region.defined_vars))
    try:
        text = region.editor.root.text()
    except Exception:
        return ""
    left = text.split("=")[0].split(":")[0].split("≔")[0].strip()
    return left if left.replace(".", "").replace("_", "").isalnum() else ""


def rules_for(item, settings) -> list:
    own = getattr(item, "cond_rules", None)
    if own:
        return own
    store = getattr(settings, "calc_rules", None) or {}
    presets = store.get("presets", {})
    preset = getattr(item, "cond_preset", "")
    if preset:
        return presets.get(preset, [])
    region = getattr(item, "region", None)
    if region is None:
        return []
    name = result_name(region)
    if not name:
        return []
    for pattern, preset_name in store.get("by_name", []):
        if pattern and fnmatch.fnmatchcase(name, pattern):
            return presets.get(preset_name, [])
    return []


def look_for(item, settings) -> tuple:
    """(font size or None, background or None) the rules give this equation now."""
    region = getattr(item, "region", None)
    if region is None:
        return None, None
    rules = rules_for(item, settings)
    if not rules:
        return None, None
    x = result_number(region)
    if x is None:
        return None, None
    size = bg = None
    for rule in rules:
        if matches(rule, x):
            if size is None and rule.get("size"):
                size = float(rule["size"])
            if bg is None and rule.get("bg"):
                bg = rule["bg"]
    return size, bg


@contextmanager
def looking(item, settings):
    """The equation as its rules have it, for laying out and drawing."""
    region = getattr(item, "region", None)
    size, bg = look_for(item, settings) if region is not None else (None, None)
    if size is None and bg is None:
        yield
        return
    own = (region.font_size, region.bg_color)
    if size is not None:
        region.font_size = size
    if bg is not None:
        region.bg_color = bg
    try:
        yield
    finally:
        region.font_size, region.bg_color = own
