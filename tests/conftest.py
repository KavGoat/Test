import gc
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PySide6.QtCore import QCoreApplication, QEvent


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    from pdf4py.app import build_application
    application = QApplication.instance() or build_application([])
    yield application


@pytest.fixture
def editor_window(qapp):
    """A main window that is torn down properly when the test is done."""
    from pdf4py.ui.mainwindow import MainWindow

    window = MainWindow()
    # Nothing in the suite may block on a modal "save your changes?" dialog.
    window.confirm_discard = lambda: True
    window.resize(1100, 820)
    yield window
    window.document.close()
    window.view.setScene(None)
    window.close()
    window.deleteLater()
    # A bare processEvents() does not deliver DeferredDelete — only a running
    # event loop does — so a suite that never enters one has to send it itself.
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    gc.collect()
    qapp.processEvents()
