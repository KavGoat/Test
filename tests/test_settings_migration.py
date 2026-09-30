"""Phase 8: on first start CalcForge takes MarkForge's settings across once —
shortcuts, tool sets and My Tools, toolbar and panel layout, dark mode and
markup defaults — and nothing else."""
from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QSettings

from calcforge import settings as app


def ini(path) -> QSettings:
    return QSettings(str(path), QSettings.IniFormat)


@pytest.fixture
def markforge(tmp_path):
    """A MarkForge settings file as MarkForge left it."""
    source = ini(tmp_path / "markforge.ini")
    source.setValue("theme", "dark")
    source.setValue("shortcuts/insert.text", "T")
    source.setValue("toolsets/sets", json.dumps([
        {"name": "My Tools", "entries": [
            {"label": "Checked stamp", "mode": "copy",
             "payload": {"type": "rect", "kind": "rect", "rect": [0, 0, 40, 20]}}]},
        {"name": "Concrete", "entries": []}]))
    source.setValue("markups/defaults", json.dumps({"rect": {"stroke": "#c92a2a"}}))
    source.setValue("toolbars/locked", True)
    source.setValue("toolbars/tools", ["rect", "cloud"])
    source.setValue("panels/sides", {"dock_pages": "right"})
    source.setValue("window/state", b"\x00\x01state")
    source.setValue("window/stamp", 41)
    source.setValue("spelling/personal", "kN\nRHS")
    source.setValue("preferences/default_author", "K. D.")
    source.sync()
    return source


def test_what_the_person_set_up_comes_across(markforge, tmp_path):
    target = ini(tmp_path / "calcforge.ini")
    copied = app.migrate_from_markforge(markforge, target)
    assert copied == sorted(["theme", "shortcuts/insert.text", "toolsets/sets",
                             "markups/defaults", "toolbars/locked", "toolbars/tools",
                             "panels/sides", "window/state"])
    assert target.value("theme") == "dark"
    assert target.value("shortcuts/insert.text") == "T"
    sets = json.loads(target.value("toolsets/sets"))
    assert [s["name"] for s in sets] == ["My Tools", "Concrete"]
    assert sets[0]["entries"][0]["label"] == "Checked stamp"
    assert json.loads(target.value("markups/defaults")) == {"rect": {"stroke": "#c92a2a"}}
    assert str(target.value("toolbars/locked")).lower() == "true"
    assert bytes(target.value("window/state")) == b"\x00\x01state"
    for key in ("window/stamp", "spelling/personal", "preferences/default_author"):
        assert not target.contains(key), f"{key} is not one of the things asked for"


def test_it_happens_once(markforge, tmp_path):
    target = ini(tmp_path / "calcforge.ini")
    app.migrate_from_markforge(markforge, target)
    target.setValue("theme", "light")                  # changed in CalcForge since
    markforge.setValue("shortcuts/insert.note", "N")   # and in MarkForge
    assert app.migrate_from_markforge(markforge, target) == []
    assert target.value("theme") == "light"
    assert not target.contains("shortcuts/insert.note")


def test_what_calcforge_already_has_is_kept(markforge, tmp_path):
    target = ini(tmp_path / "calcforge.ini")
    target.setValue("theme", "light")
    copied = app.migrate_from_markforge(markforge, target)
    assert "theme" not in copied and target.value("theme") == "light"
    assert target.value("shortcuts/insert.text") == "T"


def test_no_markforge_settings_is_fine(tmp_path):
    target = ini(tmp_path / "calcforge.ini")
    assert app.migrate_from_markforge(ini(tmp_path / "absent.ini"), target) == []
    assert target.value(app.MIGRATED_KEY) == "done"


def test_the_window_starts_with_them(markforge, tmp_path, monkeypatch, qapp):
    """End to end, through the environment the app itself reads."""
    from calcforge.app import current_theme
    from calcforge.ui import toolsets
    from calcforge.ui.mainwindow import MainWindow

    monkeypatch.setenv(app.SETTINGS_FILE_ENV, str(tmp_path / "fresh-calcforge.ini"))
    monkeypatch.setenv(app.MARKFORGE_SETTINGS_FILE_ENV, markforge.fileName())
    app.migrate_from_markforge()
    assert current_theme() == "dark"
    assert [s.name for s in toolsets.load_toolsets()] == ["My Tools", "Concrete"]
    window = MainWindow()
    try:
        assert window.shortcuts.sequence("insert.text") == "T"
        assert window.windowTitle().endswith("CalcForge")
        assert window.toolsets_panel.tree.topLevelItem(0).text(0).startswith("My Tools  (1)")
    finally:
        window.confirm_discard = lambda: True
        window.document.modified = False
        window.close()
        window.deleteLater()


def test_the_names_are_calcforges(qapp):
    from PySide6.QtWidgets import QApplication

    from calcforge.app import build_application  # noqa: F401  (the entry point exists)
    assert app.APP_NAME == "CalcForge" and app.ORGANISATION == "CalcForge"
    import calcforge
    assert "CalcForge" in calcforge.__doc__
    assert QApplication.instance() is not None
