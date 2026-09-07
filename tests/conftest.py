import gc
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Where the settings, the recovery folder and every other remembered thing go.
# This has to be done before Qt is asked for any of them, and before anything
# creates a QSettings, which is why it is here and not in a fixture: Qt works
# out those locations once and keeps the answer. Without it the suite reads and
# writes the real ones, so a test that saves an arrangement leaves it behind
# for the next run — and for whoever is using the application on this machine.
_SANDBOX = tempfile.mkdtemp(prefix="markforge-tests-")
for _variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                  "XDG_STATE_HOME"):
    os.environ[_variable] = os.path.join(_SANDBOX, _variable.lower())
    os.makedirs(os.environ[_variable], exist_ok=True)

import pytest
from PySide6.QtCore import QCoreApplication, QEvent


@pytest.fixture(scope="session", autouse=True)
def settings_sandbox(tmp_path_factory):
    """Keep the suite out of the real settings file.

    Shortcuts, the window layout and the theme are all remembered between
    sessions. Without this, a test that rebinds a key would change what every
    later test — and the developer's own copy of the app — starts with.
    """
    from PySide6.QtCore import QSettings

    folder = os.environ["XDG_CONFIG_HOME"]
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, folder)
    QSettings.setPath(QSettings.IniFormat, QSettings.SystemScope, folder)
    written = QSettings("MarkForge", "MarkForge").fileName()
    assert written.startswith(_SANDBOX), (
        f"the suite is writing its settings to {written}, which is somebody's "
        "real ones")
    yield folder


@pytest.fixture(autouse=True)
def fresh_clipboard(qapp):
    """No test inherits what the one before it copied."""
    yield
    qapp.clipboard().clear()


@pytest.fixture(autouse=True)
def fresh_modifiers(qapp):
    """No test inherits a modifier key the one before it left down.

    ``QTest.keyClick`` records the modifiers it is given and they stay
    recorded: after a Ctrl+Alt shortcut the application still answers
    ``keyboardModifiers() == ControlModifier``. The view reads that live state
    on purpose — a Ctrl held before the window had the keyboard has to count —
    so a leaked Ctrl quietly turns grid snapping off for whatever runs next,
    and the test that catches it is never the test that caused it.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QWidget

    yield
    if QApplication.keyboardModifiers() != Qt.NoModifier:
        spare = QWidget()
        spare.show()
        QTest.keyClick(spare, Qt.Key_Shift, Qt.NoModifier)
        spare.close()
        spare.deleteLater()


@pytest.fixture(autouse=True)
def fresh_settings(settings_sandbox):
    """Every test starts from the shipped defaults.

    A test that rebinds a key or moves a panel saves it, and the next window
    would open with that arrangement. Each test gets a clean slate instead.
    """
    from PySide6.QtCore import QSettings

    settings = QSettings("MarkForge", "MarkForge")
    settings.clear()
    settings.sync()
    yield
    settings.clear()
    settings.sync()


@pytest.fixture(scope="session")
def qapp(settings_sandbox):
    from markforge.app import build_application
    from PySide6.QtWidgets import QApplication
    application = QApplication.instance() or build_application([])
    yield application
    # A picture left on the clipboard outlives the application that owns it,
    # and the X server it was handed to is torn down underneath it — which
    # crashes on the way out and makes a clean run look like a broken one.
    application.clipboard().clear()


@pytest.fixture
def window(qapp):
    from markforge.ui.mainwindow import MainWindow

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
