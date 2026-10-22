"""Excel's status bar in the workbook view (docs/qa/excel_audit.md, D1-D2).

While a sheet is shown alone the footer is Excel's: on the left the cell
mode — Ready, Enter (typing into a cell), Edit (F2) or Point (a reference
being picked for a formula) — and, with more than one cell picked, the
Average, Count and Sum of what they hold; on the right the view buttons
Normal, Page Layout and Page Break Preview, a zoom slider, and the zoom box.
What belongs to the paper (the pointer's position in millimetres, the
scale, snapping, the page layout, window sync and the paper size) is put
away until the pages are shown again; nothing is lost, it comes back as it
was.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QToolButton, QWidget

#: The footer's paper controls, put away in the workbook view.
PAPER_CONTROLS = ("status_position", "status_size", "window_sync", "status_snap",
                  "status_scroll", "status_fit", "status_scale", "status_dimmer",
                  "status_toggles")


def refresh_soon(window) -> None:
    """Once the events in hand are done: typing and picking cells ask for
    it on every change, and the sums are worked out once."""
    if window is None:
        return
    timer = getattr(window, "_sheet_status_timer", None)
    if timer is None:
        timer = window._sheet_status_timer = QTimer(window)
        timer.setSingleShot(True)
        timer.setInterval(0)
        timer.timeout.connect(lambda: refresh(window))
    timer.start()


def _widgets(window) -> Optional[dict]:
    made = getattr(window, "_sheet_status", None)
    if made is not None:
        return made
    status = window.statusBar()
    if status is None or not hasattr(window, "zoom_combo"):
        return None
    mode = QLabel("Ready")
    mode.setObjectName("sheetMode")
    mode.setToolTip("Excel's cell mode: Ready, Enter (typing in), Edit (F2) or Point "
                    "(picking a reference for a formula)")
    stats = QLabel("")
    stats.setObjectName("sheetStats")
    stats.setToolTip("Of the cells picked: the average and sum of their numbers, and how "
                     "many are not empty")
    views = QWidget()
    views.setObjectName("sheetViews")
    row = QHBoxLayout(views)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    buttons = {}
    from .sheetview import BREAK_PREVIEW, NORMAL, PAGE_LAYOUT, set_view
    for key, text, tip in ((NORMAL, "Normal", "Normal: the sheet alone, as Excel opens it"),
                           (PAGE_LAYOUT, "Page Layout", "Page Layout: the sheet's pages"),
                           (BREAK_PREVIEW, "Page Break Preview",
                            "Page Break Preview: what prints white, the rest grey, the page "
                            "breaks in blue to drag")):
        button = QToolButton()
        button.setObjectName(f"sheetView_{key}")
        button.setText(text)
        button.setToolTip(tip)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.clicked.connect(lambda _on=False, k=key: set_view(window, k))
        row.addWidget(button)
        buttons[key] = button
    slider = QSlider(Qt.Horizontal)
    slider.setObjectName("sheetZoomSlider")
    slider.setRange(10, 400)
    slider.setFixedWidth(110)
    slider.setToolTip("Zoom (Excel's 10 % to 400 %)")
    slider.valueChanged.connect(lambda value: _slid(window, value))
    status.addWidget(mode)
    status.addWidget(stats)
    # Excel's order at the right: the view buttons, the slider, the zoom
    # (the zoom box and the » taken off and put back after them)
    tail = [w for w in (window.zoom_combo, getattr(window, "status_more", None)) if w is not None]
    shown = [w.isVisible() for w in tail]
    for widget in tail:
        status.removeWidget(widget)
    status.addPermanentWidget(views)
    status.addPermanentWidget(slider)
    for widget, was in zip(tail, shown):
        status.addPermanentWidget(widget)
        widget.setVisible(was)
    for widget in (mode, stats, views, slider):
        widget.hide()
    made = window._sheet_status = {"mode": mode, "stats": stats, "views": views,
                                   "buttons": buttons, "slider": slider,
                                   "droppable": None}
    return made


def _slid(window, value: int) -> None:
    made = getattr(window, "_sheet_status", None)
    if made is None or made.get("quiet"):
        return
    from .sheetview import view_zoom
    window.view.set_zoom(view_zoom(window.view, value / 100.0))


def mode_of(tables) -> str:
    """Excel's cell mode for the table editor *tables*."""
    if tables is None or getattr(tables, "editor", None) is None:
        return "Ready"
    if not getattr(tables, "enter_mode", True):
        return "Edit"
    try:
        if tables._pointing():
            return "Point"
    except Exception:  # noqa: BLE001 - a mode word is never worth an error
        pass
    return "Enter"


def _number(value: float) -> str:
    text = f"{value:.10g}"
    return text if "e" in text or "." not in text else text.rstrip("0").rstrip(".")


def sums(item, ranges) -> Optional[tuple]:
    """(average or None, count, sum or None) of the cells in *ranges* of
    *item*'s sheet, or None when only one cell is picked."""
    if item is None or item.sheet is None or not ranges:
        return None
    if len(ranges) == 1 and ranges[0][0] == ranges[0][2] and ranges[0][1] == ranges[0][3]:
        return None
    count, total, numbers = 0, 0.0, 0
    seen = set()
    for (row, col), cell in item.sheet.cells.items():
        if (row, col) in seen:
            continue
        if not any(t <= row <= b and l <= col <= r for t, l, b, r in ranges):
            continue
        value = cell.value
        if value is None or value == "":
            continue
        seen.add((row, col))
        count += 1
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += float(value)
            numbers += 1
    if not count:
        return None
    return (total / numbers if numbers else None, count, total if numbers else None)


def refresh(window) -> None:
    """The footer as the view now is: Excel's in the workbook view, the
    paper's otherwise."""
    from shiboken6 import isValid
    if window is None or not isValid(window):
        return
    made = _widgets(window)
    if made is None:
        return
    from .sheetview import _item, current_view, is_on, run_shown
    status = window.statusBar()
    on = is_on(window)
    sheet_parts = [made["slider"], made["views"], made["stats"]]   # (the first goes first)
    if on and made["droppable"] is None:
        # the paper's controls put away, and kept from coming back for room;
        # Excel's own dropped, the slider first, when the footer is short
        made["droppable"] = list(getattr(status, "_droppable", []))
        for name in PAPER_CONTROLS:
            widget = getattr(window, name, None)
            if widget is not None:
                widget.hide()
        made["mode"].show()
        if hasattr(status, "set_droppable"):
            status.set_droppable(sheet_parts, window.status_more)
        else:
            for widget in sheet_parts:
                widget.show()
    elif not on and made["droppable"] is not None:
        kept, made["droppable"] = made["droppable"], None
        for key in ("mode", "stats", "views", "slider"):
            made[key].hide()
        if hasattr(status, "set_droppable"):
            status.set_droppable(kept, window.status_more)
    # nothing between the sheet tabs and the footer (M1): the closed
    # Markups List's bar goes while a sheet is shown alone
    split = getattr(window, "bottom_split", None)
    if split is not None and split.count() > 1:
        opened = getattr(window, "markups_list_open", lambda: False)()
        if on and not opened:
            if made.get("handle_width") is None:
                made["handle_width"] = split.handleWidth()
                split.setHandleWidth(0)
        elif made.get("handle_width") is not None:
            split.setHandleWidth(made.pop("handle_width"))
    if not on:
        return
    tables = window.view.tables
    made["mode"].setText(mode_of(tables))
    item = _item(window, run_shown(window.scene))
    text = ""
    if item is not None and tables.item is item and tables.active is not None:
        got = sums(item, picked_ranges(tables))
        if got is not None:
            average, count, total = got
            parts = []
            if average is not None:
                parts.append(f"Average: {_number(average)}")
            parts.append(f"Count: {count}")
            if total is not None:
                parts.append(f"Sum: {_number(total)}")
            text = "    ".join(parts)
    made["stats"].setText(text)
    which = current_view(window)
    for key, button in made["buttons"].items():
        button.setChecked(key == which)
    from .sheetview import shown_zoom
    made["quiet"] = True
    made["slider"].setValue(int(round(shown_zoom(window.view) * 100)))
    made["quiet"] = False


def picked_ranges(tables) -> list:
    """Every block picked: the selection, and those added with Ctrl."""
    ranges = [tuple(tables.selection())]
    for extra in getattr(tables, "extra_ranges", None) or ():
        if tuple(extra) not in ranges:
            ranges.append(tuple(extra))
    return ranges
