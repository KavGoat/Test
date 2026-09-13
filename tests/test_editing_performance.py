"""Avoid intermediate panel rebuilds while retaining complete edit history."""
from PySide6.QtCore import QPointF, QRectF, Qt
from markforge.items.shapes import RectItem
from tests.test_usability import press_key, hover
from markforge.items.base import Style
from dataclasses import asdict


def test_bulk_restore_publishes_only_the_finished_page(window):
    frame = window.view.frame()
    for i in range(25):
        frame.add_markup(RectItem(rect=QRectF(0, 0, 20, 20)), QPointF(30 + i, 40))
    before = frame.serialize_items()
    seen = []
    frame.itemsChanged.connect(lambda: seen.append(frame.serialize_items()))
    frame.load_items(before)
    assert seen == [before]
    assert len(window.markups_panel._rows) == len(before)
    frame.load_items([])
    assert seen == [before, []]
    assert window.markups_panel._rows == []


def test_nudge_undo_redo_keeps_state_selection_and_panels(window, qapp):
    frame = window.view.frame()
    for i in range(12):
        frame.add_markup(RectItem(rect=QRectF(0, 0, 20, 20)), QPointF(80 + i * 25, 100))
    chosen = frame.markups()[3]
    chosen.setSelected(True)
    uid = chosen.uid
    before = frame.serialize_items()
    press_key(window.view, Qt.Key_Right)
    after = frame.serialize_items()
    assert after != before
    for action, expected in [(window.undo_stack.undo, before),
                             (window.undo_stack.redo, after)]:
        action()
        qapp.processEvents()
        assert frame.serialize_items() == expected
        assert [i.uid for i in frame.markups() if i.isSelected()] == [uid]
        assert len(window.markups_panel._rows) == len(expected)


def test_style_snapshots_preserve_values_and_detach_custom_dashes():
    style = Style(stroke='#123456', hatch='cross', hatch_scale=2.5,
                  dash_array=[2.0, 3.0])
    data, copy = style.to_dict(), style.copy()
    assert data == asdict(style)
    assert copy == style
    style.dash_array[0] = 9.0
    style.stroke = '#abcdef'
    assert data['dash_array'] == [2.0, 3.0]
    assert copy.dash_array == [2.0, 3.0]
    assert data['stroke'] == copy.stroke == '#123456'


def test_pointer_snapping_tracks_movement_rotation_visibility_and_undo(window):
    frame, view = window.view.frame(), window.view
    item = frame.add_markup(RectItem(rect=QRectF(0, 0, 40, 30)), QPointF(100, 100))
    settings = window.document.settings
    settings.snap_to_grid = settings.snap_to_alignment = False
    settings.snap_to_items = True
    window.select_tool('line')

    def aim(point):
        hover(view, point.x() + 1, point.y() + 1)
        return view._snap_marker

    start = item.mapToScene(QPointF())
    assert aim(start) == start
    view.begin_snapshot([frame])
    item.setPos(300, 300)
    item.setRotation(90)
    view.commit_snapshot('Move and rotate')
    assert aim(start) is None
    end = item.mapToScene(QPointF(40, 30))
    assert aim(end) == end
    item.setVisible(False)
    assert aim(end) is None
    item.setVisible(True)
    window.undo_stack.undo()
    assert aim(start) == start
    assert aim(end) is None
