"""Reproducible editing latency: python tools/benchmark_editing.py --items 500.

Uses actual Qt pointer/key events and the normal panels and undo stack. Fixture
construction is excluded. Timings include synchronous UI work; queued paints
are drained after every sample. Settings are isolated from the user's session.
"""
import argparse
import cProfile
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_sandbox = tempfile.TemporaryDirectory(prefix="markforge-edit-benchmark-")
os.environ['MARKFORGE_SETTINGS_FILE'] = str(Path(_sandbox.name) / 'settings.ini')

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QSignalBlocker
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from markforge.app import build_application
from markforge.items.shapes import RectItem
from markforge.ui.mainwindow import MainWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--items', type=int, default=500)
    parser.add_argument('--rounds', type=int, default=5)
    parser.add_argument('--profile')
    args = parser.parse_args()
    if args.items < 1 or args.rounds < 1:
        parser.error('items and rounds must be positive')
    app = build_application([])
    win = MainWindow()
    win.confirm_discard = lambda: True
    win.interactive_prompts = False
    win.resize(1280, 860)
    win.show()
    app.processEvents()
    view = win.view
    view.set_zoom(1)
    frame = view.frame()
    with QSignalBlocker(frame):
        for i in range(args.items):
            item = RectItem(rect=QRectF(0, 0, 12, 12))
            item.setZValue(i + 1)
            frame.add_markup(item, QPointF(30 + (i % 25) * 20, 40 + (i // 25) * 20))
    win.refresh_lists()
    frame.markups()[0].setSelected(True)
    view.setFocus()
    app.processEvents()
    initial = frame.serialize_items()
    samples = {'pointer': [], 'nudge': [], 'undo': [], 'redo': []}
    profile = cProfile.Profile() if args.profile else None
    if profile:
        profile.enable()
    def measure(name, action):
        start = time.perf_counter()
        action()
        app.processEvents()
        samples[name].append((time.perf_counter() - start) * 1000)
    def move_pointer(point):
        local = view.mapFromScene(frame.mapToScene(point))
        app.sendEvent(view.viewport(), QMouseEvent(
            QEvent.MouseMove, QPointF(local),
            QPointF(view.viewport().mapToGlobal(local)),
            Qt.NoButton, Qt.NoButton, Qt.NoModifier))
    for round_index in range(args.rounds):
        win.select_tool('line')
        for i in range(20):
            measure('pointer', lambda i=i: move_pointer(
                QPointF(35 + i * 7, 45 + round_index % 5)))
        QTest.keyClick(view, Qt.Key_Escape)
        frame.markups()[0].setSelected(True)
        measure('nudge', lambda: QTest.keyClick(view, Qt.Key_Right))
        changed = frame.serialize_items()
        assert changed != initial, ('Nudge did not edit the selected markup', round_index,
                                    len(win.scene.selectedItems()), view.tool_key)
        measure('undo', win.undo_stack.undo)
        assert frame.serialize_items() == initial, 'Undo lost document state'
        measure('redo', win.undo_stack.redo)
        assert frame.serialize_items() == changed, 'Redo lost document state'
        win.undo_stack.undo()
        app.processEvents()
    if profile:
        profile.disable()
        profile.dump_stats(args.profile)
    print(json.dumps({'items': args.items, 'rounds': args.rounds,
                      'platform': sys.platform, 'qt_platform': app.platformName(),
                      'milliseconds': {name: {'median': statistics.median(values),
                                             'max': max(values), 'samples': values}
                                       for name, values in samples.items()}}, indent=2))
    win.document.modified = False
    win.close()
    app.processEvents()


if __name__ == '__main__':
    main()
