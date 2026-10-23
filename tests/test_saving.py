"""Saving when the file can't be written, as Office does: why, in plain
words, and Try Again, Save As… or Cancel; files already there asked about
before they are replaced (the user, 2026-10-24: "trying to save a file and
have things like replace or try again if it cant save etc.")."""
from __future__ import annotations

import os
import stat

import pytest

from calcforge.io import project as project_io
from calcforge.ui import saving
from tests.test_calc_saving import save_to


@pytest.fixture
def w(window):
    window.show()
    return window


def changed(w) -> None:
    """Something to save: a page more."""
    w.add_page(len(w.document.pages) - 1)


def test_a_read_only_file_is_left_as_it_was_and_says_why(w, tmp_path):
    path = str(tmp_path / "calc.pdf")
    save_to(w, path)
    before = open(path, "rb").read()
    revision = w.document.revision
    changed(w)
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP)
    try:
        w.save_failure_answer = saving.CANCEL
        assert not w.save_document()
        assert w.save_failure_said == "calc.pdf couldn't be saved: the file is read-only."
        assert open(path, "rb").read() == before, "the file that was there is as it was"
        assert w.document.revision == revision, "no revision for a save that wasn't"
        assert not w.undo_stack.isClean(), "still to be saved"
    finally:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def test_try_again_saves_once_the_other_program_lets_go(w, tmp_path, monkeypatch):
    path = str(tmp_path / "calc.pdf")
    save_to(w, path)
    changed(w)
    real = project_io.save_document
    tries = []

    def held_once(document, target, *args, **kwargs):
        tries.append(target)
        if len(tries) == 1:
            raise PermissionError(13, "Access is denied", target)   # open elsewhere
        return real(document, target, *args, **kwargs)
    monkeypatch.setattr(project_io, "save_document", held_once)
    answers = iter([saving.RETRY])
    w.save_failure_answer = lambda text: next(answers)
    assert w.save_document()
    assert len(tries) == 2 and w.undo_stack.isClean()
    assert "open in another program" in w.save_failure_said
    assert "close it there and try again" in w.save_failure_said


def test_save_as_after_a_failure_saves_somewhere_else(w, tmp_path):
    gone = tmp_path / "gone"
    w.document.path = str(gone / "calc.pdf")               # a folder since taken away
    changed(w)
    here = str(tmp_path / "here.pdf")
    w.save_failure_answer = saving.SAVE_AS
    w.save_as_answer = here
    assert w.save_document()
    assert "isn't there" in w.save_failure_said
    assert w.document.path == here and os.path.exists(here)
    assert not gone.exists()


def test_cancel_after_save_as_keeps_the_name_it_had(w, tmp_path):
    gone = str(tmp_path / "gone" / "calc.pdf")
    w.document.path = gone
    changed(w)
    w.save_failure_answer = saving.SAVE_AS
    w.save_as_answer = ""                                   # the dialog cancelled
    assert not w.save_document()
    assert w.document.path == gone


def test_save_as_never_writes_over_a_document_open_in_another_tab(w, tmp_path):
    first = str(tmp_path / "first.pdf")
    save_to(w, first)
    w.open_in_new_tab()
    changed(w)
    other = str(tmp_path / "other.pdf")
    answers = iter([first, other])
    w.save_as_answer = lambda start: next(answers)
    assert w.save_document_as()
    assert w.told == ["first.pdf is open in another tab or window: save under another "
                      "name, or close it there first."]
    assert w.document.path == other and os.path.exists(other)


def test_split_asks_before_replacing_files_already_there(w, tmp_path):
    changed(w)                                              # two pages: two parts
    folder = str(tmp_path)
    there = os.path.join(folder, "document part 1.pdf")
    with open(there, "wb") as handle:
        handle.write(b"kept")
    w.replace_answer = False
    assert w.split_into_files(every=1, folder=folder) == []
    assert w.replace_said == "document part 1.pdf is already there. Replace it?"
    assert open(there, "rb").read() == b"kept"
    w.replace_answer = True
    made = w.split_into_files(every=1, folder=folder)
    assert [os.path.basename(p) for p in made] == ["document part 1.pdf", "document part 2.pdf"]
    assert open(there, "rb").read().startswith(b"%PDF")


def test_export_to_pdf_into_a_missing_folder_offers_another_place(w, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(tmp_path / "gone" / "out.pdf"), ""))
    w.save_failure_answer = saving.SAVE_AS
    w.save_as_answer = str(tmp_path / "out.pdf")
    w.export_pdf()
    assert "isn't there" in w.save_failure_said
    assert os.path.exists(tmp_path / "out.pdf")
    assert w.status_hint.text() == f"Exported {tmp_path / 'out.pdf'}"


def test_the_markups_lists_export_says_why_instead_of_raising(w, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(tmp_path / "gone" / "markups.csv"), ""))
    w.save_failure_answer = saving.CANCEL
    w.markups_panel.export_csv()
    assert w.save_failure_said.startswith("markups.csv couldn't be saved: the folder ")


def test_why_puts_it_as_a_person_would(tmp_path):
    import errno
    target = str(tmp_path / "a.pdf")
    assert saving.why(OSError(errno.ENOSPC, "No space left on device"), target) == \
        "the disk is full"
    assert saving.why(PermissionError(13, "denied"), str(tmp_path / "new.pdf")) == \
        "you aren't allowed to save in that folder"
    assert saving.why(RuntimeError("the page couldn't be drawn"), target) == \
        "the page couldn't be drawn"
