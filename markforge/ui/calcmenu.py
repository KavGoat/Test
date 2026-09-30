"""An equation's settings (decision 20): SMath's right-click menu.

The menu is WebSMath's (its ``WorksheetView.context_menu``, SMath Cloud's
item for item): Display input data, Go to definition, Show description,
Disable evaluation, Ignore units, Optimization, Decimal places, Exponential
threshold, Fractions and Rounding — and for a plot, Plot settings, Grid, Axes
and Graph by points. Font and colour are added, as decision 20 asks.

A setting changes every selected equation, and is one undo step. The
document's own format (Preferences) is marked with * as SMath marks the
worksheet default.
"""
from __future__ import annotations

import dataclasses

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QMenu

# Set by tests to answer a colour dialog without showing it: {title: "#rrggbb"}.
ANSWERS: dict = {}

FONT_SIZES = (8, 9, 10, 11, 12, 14, 16, 18, 20, 24)


def equations_for(window, item) -> list:
    """The equations a setting applies to: every selected one, *item* first."""
    chosen = [i for i in window.selected_items() if getattr(i, "IS_CALC", False)
              and getattr(i, "region", None) is not None]
    if item not in chosen:
        chosen = [item]
    return chosen


def change(window, items: list, description: str, apply, refresh: bool = True) -> None:
    """Apply *apply(region)* to each equation, recalculate, one undo step."""
    from ..calc.docsheet import sheet_for

    items = [i for i in items if not getattr(i, "locked", False)]
    if not items:
        return
    view = window.view
    view.begin_snapshot(view.involved_frames(*items))
    sheet = sheet_for(window.document)
    for item in items:
        apply(item.region)
        # a setting changes what the region shows and, for Disable evaluation
        # or Ignore units, what it defines: recalculate like leaving it
        sheet.worksheet.update_after_edit(item.region)
    sheet._report()
    for item in items:
        if item._view is not None:
            item._view._plot_cache = None      # a plot keeps a drawing of itself
        item.relayout()
        item.update()
    view.commit_snapshot(description)
    if refresh:                            # (not from the Properties panel itself)
        window.refresh_selection()


def fill(window, menu: QMenu, item) -> None:
    """Add the equation's settings to the top of *menu*."""
    from ..calc.docsheet import sheet_for

    region = item.region
    items = equations_for(window, item)
    worksheet = sheet_for(window.document).worksheet

    def check(into, title, on, apply, description=None, enabled=True):
        action = into.addAction(title)
        action.setCheckable(True)
        action.setChecked(bool(on))
        action.setEnabled(enabled)
        action.triggered.connect(
            lambda _=False: change(window, items, description or title, apply))
        return action

    if region.plot is not None:
        state = region.plot
        menu.addAction("Plot settings…", lambda: plot_settings(window, item))
        for title, attr in (("Grid", "grid"), ("Axes", "axes"), ("Graph by points", "points")):
            check(menu, title, getattr(state, attr),
                  lambda r, a=attr: setattr(r.plot, a, not getattr(r.plot, a)))
        menu.addSeparator()
        return
    if region.kind != "math":
        return

    fmt = region.fmt or worksheet.format
    base = worksheet.format

    def set_fmt(**changes):
        def apply(r):
            made = dataclasses.replace(r.fmt or worksheet.format, **changes)
            r.fmt = None if made == worksheet.format else made
        return apply

    equation = menu.addMenu("Equation")
    check(equation, "Display input data", region.show_input,
          lambda r: setattr(r, "show_input", not r.show_input))
    equation.addSeparator()
    equation.addAction("Go to definition", lambda: go_to_definition(window, item))
    description = equation.addAction("Show description")
    description.setEnabled(False)          # as WebSMath: not supported yet
    check(equation, "Disable evaluation", not region.enabled,
          lambda r: setattr(r, "enabled", not r.enabled))
    equation.addSeparator()
    check(equation, "Ignore units", region.ignore_units,
          lambda r: setattr(r, "ignore_units", not r.ignore_units))
    equation.addSeparator()
    optimization = equation.addMenu("Optimization")
    current = region.optimization or ("numeric" if region.editor.evaluate else "symbolic")
    for key, title in (("symbolic", "Symbolic"), ("numeric", "Numeric"), ("none", "None")):
        check(optimization, title, current == key,
              lambda r, k=key: setattr(r, "optimization", k), f"Optimization: {title}")

    places = equation.addMenu("Decimal places")
    check(places, "Trailing zeros", fmt.trailing_zeros,
          set_fmt(trailing_zeros=not fmt.trailing_zeros))
    places.addSeparator()
    check(places, "Significant figures mode", fmt.significant,
          set_fmt(significant=not fmt.significant))
    places.addSeparator()
    for n in range(16):
        check(places, f"{n} *" if n == base.decimals else str(n), fmt.decimals == n,
              set_fmt(decimals=n), f"Decimal places: {n}")
    threshold = equation.addMenu("Exponential threshold")
    for n in range(16):
        check(threshold, f"{n} *" if n == base.threshold else str(n), fmt.threshold == n,
              set_fmt(threshold=n), f"Exponential threshold: {n}")
    fractions = equation.addMenu("Fractions")
    for key, title in (("decimal", "Decimal"), ("fraction", "Fraction"), ("auto", "Auto")):
        check(fractions, title, fmt.fractions == key, set_fmt(fractions=key),
              f"Fractions: {title}")
    check(fractions, "Default", region.fmt is None, lambda r: setattr(r, "fmt", None),
          "Result format: default")
    fractions.addSeparator()
    check(fractions, "Use mixed numbers", fmt.mixed, set_fmt(mixed=not fmt.mixed),
          enabled=fmt.fractions != "decimal")
    rounding = equation.addMenu("Rounding")
    check(rounding, "Half to even", fmt.half_even, set_fmt(half_even=True))
    check(rounding, "Away from zero", not fmt.half_even, set_fmt(half_even=False))

    equation.addSeparator()
    font = equation.addMenu("Font")
    for size in FONT_SIZES:
        check(font, f"{size} pt", abs(region.font_size - size) < 0.01,
              lambda r, s=size: setattr(r, "font_size", float(s)), f"Font size {size} pt")
    font.addSeparator()
    for attr, title in (("bold", "Bold"), ("italic", "Italic"), ("underline", "Underline")):
        check(font, title, getattr(region, attr),
              lambda r, a=attr: setattr(r, a, not getattr(r, a)))
    equation.addAction("Colour…", lambda: choose_colour(window, items, "color", "Colour"))
    equation.addAction("Background…",
                       lambda: choose_colour(window, items, "bg_color", "Background"))
    check(equation, "Border", region.border, lambda r: setattr(r, "border", not r.border))
    menu.addSeparator()


def choose_colour(window, items, attr: str, title: str) -> None:
    first = items[0].region
    if title in ANSWERS:
        picked = QColor(ANSWERS[title])
    else:
        picked = QColorDialog.getColor(QColor(getattr(first, attr)), window, title)
    if not picked.isValid():
        return
    change(window, items, title, lambda r: setattr(r, attr, picked.name()))


def go_to_definition(window, item) -> None:
    """Focus the equation that defines the name at the cursor, or the first
    name the equation uses (WebSMath's go_to_definition)."""
    from ..calc.docsheet import sheet_for
    from ..items.calc import CalcItem

    region = item.region
    _start, word = region.editor.current_word()
    # the name at the cursor first; a number there (the cursor after "+1")
    # means nothing, so the names the equation uses are tried after it
    names = ([word] if word and not word[0].isdigit() else []) + sorted(region.uses)
    worksheet = sheet_for(window.document).worksheet
    by_region = {i.region.id: i for page in window.document.pages if page.frame is not None
                 for i in page.frame.markups() if isinstance(i, CalcItem) and i.region}
    for name in names:
        for other in sorted(worksheet.regions, key=lambda r: r.key, reverse=True):
            if other.key < region.key and (name in other.defined_vars or
                                           any(n == name for n, _ in other.defined_funcs)):
                target = by_region.get(other.id)
                if target is not None:
                    window.view.calc.focus(target, target.sceneBoundingRect().center())
                    window.view.centerOn(target)
                    return


def plot_settings(window, item) -> None:
    """The plot's shown ranges, grid, axes and lines/points (WebSMath's)."""
    from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                                   QFormLayout, QRadioButton)

    from ..calc.plot import fit_ranges

    state = item.region.plot
    if "Plot settings" in ANSWERS:
        chosen = ANSWERS["Plot settings"]
    else:
        dialog = QDialog(window)
        dialog.setWindowTitle("Plot settings")
        form = QFormLayout(dialog)
        (x0, x1), (y0, y1) = state.x_range(), state.y_range()
        boxes = []
        for label, value in (("x from", x0), ("x to", x1), ("y from", y0), ("y to", y1)):
            box = QDoubleSpinBox()
            box.setDecimals(4)
            box.setRange(-1e9, 1e9)
            box.setValue(value)
            form.addRow(label + ":", box)
            boxes.append(box)
        grid, axes = QCheckBox("Grid"), QCheckBox("Axes")
        grid.setChecked(state.grid)
        axes.setChecked(state.axes)
        lines, points = QRadioButton("Lines"), QRadioButton("Points")
        (points if state.points else lines).setChecked(True)
        for widget in (grid, axes, lines, points):
            form.addRow(widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        chosen = ([b.value() for b in boxes], grid.isChecked(), axes.isChecked(),
                  points.isChecked())
    ranges, grid_on, axes_on, points_on = chosen

    def apply(region):
        try:
            fit_ranges(region.plot, *ranges)
        except ValueError:
            window.status_hint.setText(
                "The range is empty: 'to' must be larger than 'from'.")
        region.plot.grid, region.plot.axes, region.plot.points = grid_on, axes_on, points_on
    change(window, [item], "Plot settings", apply)
