"""No widget is left lying about as a window of its own.

A widget made with no parent is a top-level window of the application,
owned by Python, and freed whenever the collector next runs. When that fell
in the middle of PySide turning the application's list of windows into
Python objects, the list held a freed window: a segmentation fault (three
workers of the every-command run, 2026-10-19, all in the harness's walk of
QApplication.topLevelWidgets()). The two found: the throwaway line-end list
the Properties toolbar made on each theme change to copy its pictures, and
Set Scale's name box and page range, made but not placed when unused.
"""
import gc

import shiboken6
from PySide6.QtWidgets import QApplication

from calcforge.ui import dialogs, propbar
from calcforge.ui.mainwindow import MainWindow


def _strays(collect=True):
    """Python-owned windows with no parent, other than the main windows."""
    if collect:
        gc.collect()
    gc.disable()                    # no collecting while the list is read
    try:
        return [f"{type(w).__name__} {w.objectName()}"
                for w in QApplication.topLevelWidgets()
                if shiboken6.ownedByPython(w) and w.parentWidget() is None
                and not isinstance(w, MainWindow)]
    finally:
        gc.enable()


def test_a_theme_change_leaves_no_line_end_list_behind(window):
    before = _strays()
    gc.disable()        # what is left must be gone by itself, not by a collection
    try:
        for dark in (True, False, True, False):
            window.act_dark.setChecked(dark)
            QApplication.processEvents()
        propbar.refresh_icons(window)
        assert _strays(collect=False) == before
    finally:
        gc.enable()


def test_set_scale_keeps_its_unused_boxes_as_its_own(window):
    before = _strays()
    for name in (None, "Detail A"):          # pages, then a viewport's name
        dialog = dialogs.ScaleDialog(window.current_page().scale, None, window, name=name)
        assert dialog.name.parentWidget() is not None
        assert dialog.pages.parentWidget() is not None
        dialog.deleteLater()
    assert _strays() == before
