"""What can be changed about each markup after it has been drawn."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGroupBox,
                               QLineEdit, QPlainTextEdit, QPushButton, QSpinBox)
from tests.test_usability import click, double_click, drag, hover, markups, press_key
from markforge.ui.tools import TOOLS


def test_audit(window):
    from markforge.ui import tools as tool_module
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
