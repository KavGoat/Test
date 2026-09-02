import gc
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PySide6.QtCore import QCoreApplication, QEvent


@pytest.fixture(scope="session")
def qapp():
    from calcforge.app import build_application
    from PySide6.QtWidgets import QApplication
    application = QApplication.instance() or build_application([])
    yield application


@pytest.fixture
def window(qapp):
    from calcforge.ui.mainwindow import MainWindow

    main = MainWindow()
    # Nothing in the suite may block on a modal "save your changes?" dialog.
    main.confirm_discard = lambda: True
    # Prompts are opened deliberately by the tests that exercise them.
    main.interactive_prompts = False
    main.resize(1280, 860)
    # 1:1 zoom keeps synthesised view coordinates aligned with scene points.
    main.view.set_zoom(1.0)
    yield main
    main.document.modified = False
    main.undo_stack.clear()
    main.view.deactivate_table()
    main.view.setScene(None)
    for page in main.document.pages:
        page.frame = None
    main.close()
    main.setParent(None)
    main.deleteLater()
    # Windows left alive make every later app-wide restyle slower, so make sure
    # Qt has actually finished with this one before the next test builds another.
    for _ in range(3):
        qapp.processEvents()
    # A bare processEvents() does not deliver DeferredDelete — only a running
    # event loop does — so a suite that never enters one has to send it itself.
    # Without this every window built by an earlier test stays alive and each
    # application-wide restyle gets slower.
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    gc.collect()
    qapp.processEvents()
