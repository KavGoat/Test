"""What can be changed about each markup after it has been drawn."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGroupBox,
                               QLineEdit, QPlainTextEdit, QPushButton, QSpinBox)
from tests.test_usability import click, double_click, drag, hover, markups, press_key
from calcforge.ui.tools import TOOLS


def make(window, key):
    """Draw one of whatever this tool draws, and give it back."""
    before = set(markups(window))
    tool = next(t for t in TOOLS if t.key == key)
    window.select_tool(key)
    if tool.mode == "click":
        click(window.view, 200, 200)
    elif tool.mode == "poly":
        for x, y in ((150, 400), (300, 400), (300, 520), (150, 520)):
            click(window.view, x, y)
            hover(window.view, x, y)
        window.view.finish_poly()
    elif tool.mode == "anchor":
        click(window.view, 120, 600)
        drag(window.view, 250, 560, 420, 620)
    else:
        drag(window.view, 150, 150, 380, 260)
    window.view.close_label_editor(commit=False)
    if window.view.editing_item() is not None:
        item = window.view.editing_item()
        if hasattr(item, "set_text"):
            item.set_text("words")
        elif hasattr(item, "source"):
            item.source = "a := 1 m"
        window.view.end_item_edit()
    window.view.deactivate_table()
    made = [i for i in markups(window) if i not in before]
    return made[0] if made else None


def test_audit(window):
    from calcforge.ui import tools as tool_module
    lines = []
    for tool in TOOLS:
        if tool.mode == "none" and tool.key != "snapshot":
            continue
        if tool.factory is None and tool.key != "snapshot":
            continue
        if tool.key in ("image", "snapshot", "calibrate"):
            continue
        window.new_document()
        window.interactive_prompts = False
        item = make(window, tool.key)
        if item is None:
            lines.append(f"{tool.key:22} MADE NOTHING")
            continue
        window.select_tool("select")
        window.view.scene().clearSelection()
        item.setSelected(True)
        window.refresh_selection()
        panel = window.properties_panel
        groups = [g.title() for g in panel.findChildren(QGroupBox)]
        buttons = [b.text() for b in panel.findChildren(QPushButton)]
        handles = sorted(item.handle_points())
        lines.append(f"{tool.key:22} groups={groups} handles={len(handles)} "
                     f"buttons={buttons}")
    print("\n".join(lines))
