"""Cancellation while focus or mouse ownership has left the usual canvas path."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QLineEdit, QDialog

from tests.test_usability import click, press_key
from markforge.items.shapes import RectItem


def test_escape_from_inline_panel_editor_cancels_callout(window, qapp):
    tree = QTreeWidget(window)
    tree.setColumnCount(1)
    node = QTreeWidgetItem(['Rename'])
    node.setFlags(node.flags() | Qt.ItemIsEditable)
    tree.addTopLevelItem(node)
    tree.show()
    window.select_tool('callout')
    click(window.view, 150, 150)
    assert window.view._pending_anchor is not None
    tree.editItem(node, 0)
    qapp.processEvents()
    editor = tree.findChild(QLineEdit)
    assert editor is not None
    QTest.keyClick(editor, Qt.Key_Escape)
    assert window.view.tool_key == 'select'
    assert window.view._pending_anchor is None
    tree.deleteLater()


def test_escape_releases_a_stale_scene_mouse_grab(window):
    item = RectItem()
    window.view.frame().add_markup(item)
    item.grabMouse()
    assert window.view.scene().mouseGrabberItem() is item
    press_key(window.view, Qt.Key_Escape)
    assert window.view.scene().mouseGrabberItem() is None


def test_escape_in_dialog_preserves_the_canvas_tool(window):
    window.select_tool('line')
    dialog = QDialog(window)
    editor = QLineEdit(dialog)
    dialog.show()
    QTest.keyClick(editor, Qt.Key_Escape)
    assert window.view.tool_key == 'line'
    assert not dialog.isVisible()
