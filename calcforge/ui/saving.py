"""Writing a file somebody chose, as Office does when it can't be written:
what went wrong, in plain words, and Try Again, Save As… or Cancel (the
user, 2026-10-24: "trying to save a file and have things like replace or
try again if it cant save"). Files already there are asked about before
they are replaced, when no save dialog has asked already.

A failed write never touches the file that was there: what is written goes
to a file beside it first and is moved over it only once it is whole
(io/project.save_document does the same for the document itself).
"""
from __future__ import annotations

import errno
import os
import stat
import tempfile
from typing import Callable, Iterable, Optional

from PySide6.QtWidgets import QFileDialog, QMessageBox

RETRY, SAVE_AS, CANCEL = "retry", "save_as", "cancel"


def read_only(path: str) -> bool:
    """Whether the file at *path* is marked read-only (its own flag, which
    Windows' Properties ▸ Read-only sets, not only who may write it)."""
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    return not mode & stat.S_IWUSR or not os.access(path, os.W_OK)


def check_writable(path: str) -> None:
    """Refuse a read-only file before anything is written: replacing it
    whole, as a save does, would otherwise go through on some systems."""
    if os.path.isfile(path) and read_only(path):
        raise PermissionError(errno.EACCES, "the file is read-only", path)


def why(exc: BaseException, path: str) -> str:
    """What went wrong writing *path*, as a person would put it."""
    folder = os.path.dirname(os.path.abspath(path)) or "."
    code = getattr(exc, "errno", None)
    if code == errno.ENOSPC:
        return "the disk is full"
    if code == errno.EROFS:
        return "the drive it is on can only be read"
    if code == errno.ENAMETOOLONG:
        return "its name, with the folders it is in, is too long"
    if isinstance(exc, IsADirectoryError) or os.path.isdir(path):
        return "there is a folder of that name"
    if isinstance(exc, FileNotFoundError) or not os.path.isdir(folder):
        return f"the folder {folder} isn't there (moved, renamed, or a drive taken out)"
    if isinstance(exc, PermissionError) or code in (errno.EACCES, errno.EPERM):
        if os.path.isfile(path) and read_only(path):
            return "the file is read-only"
        if os.path.exists(path):
            return ("it is open in another program, or you aren't allowed to change it — "
                    "close it there and try again")
        return "you aren't allowed to save in that folder"
    text = str(exc).strip()
    return text or type(exc).__name__


def after_failure(window, path: str, exc: BaseException, title: str,
                  can_save_as: bool = True) -> str:
    """Ask what to do now *path* couldn't be written: RETRY, SAVE_AS or
    CANCEL. A test answers through ``window.save_failure_answer`` (a value,
    or a callable given the message); without prompts it is CANCEL."""
    name = os.path.basename(path) or path
    text = f"{name} couldn't be saved: {why(exc, path)}."
    window.save_failure_said = text
    status = getattr(window, "status_hint", None)
    if status is not None:
        status.setText(text)
    answer = getattr(window, "save_failure_answer", None)
    if answer is not None:
        return answer(text) if callable(answer) else answer
    if not getattr(window, "interactive_prompts", True):
        return CANCEL
    box = QMessageBox(QMessageBox.Warning, title, text, QMessageBox.NoButton, window)
    if os.path.isfile(path):
        box.setInformativeText("The file that was there is as it was.")
    retry = box.addButton("Try Again", QMessageBox.AcceptRole)
    other = box.addButton("Save As…", QMessageBox.ActionRole) if can_save_as else None
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(retry)
    box.exec()
    clicked = box.clickedButton()
    if clicked is retry:
        return RETRY
    if other is not None and clicked is other:
        return SAVE_AS
    return CANCEL


def atomically(path: str, write: Callable[[str], object]):
    """*write* to a file beside *path*, then moved over it whole: what
    *write* gave back. A failure leaves *path* as it was."""
    check_writable(path)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".calcforge-save-", suffix=os.path.splitext(path)[1],
        dir=os.path.dirname(os.path.abspath(path)))
    os.close(descriptor)
    try:
        got = write(temporary)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return got


def write_until_done(window, path: str, write: Callable[[str], object], title: str,
                     file_filter: str = "") -> Optional[tuple]:
    """*write* (given the path) until it works: (path written, what *write*
    gave back), or None when given up. Save As… asks for another place
    (with *file_filter*) and tries there."""
    while True:
        try:
            return path, atomically(path, write)
        except Exception as exc:  # noqa: BLE001  (said, not raised: the work is still here)
            answer = after_failure(window, path, exc, title, can_save_as=True)
            if answer == RETRY:
                continue
            if answer == SAVE_AS:
                path = ask_where(window, title, path, file_filter)
                if path:
                    continue
            return None


def ask_where(window, title: str, start: str, file_filter: str = "") -> str:
    """Another place to save, from the save dialog (a test answers
    through ``window.save_as_answer``); "" when cancelled."""
    answer = getattr(window, "save_as_answer", None)
    if answer is not None:
        return answer(start) if callable(answer) else answer
    path, _ = QFileDialog.getSaveFileName(window, title, start, file_filter)
    return path


def confirm_replace(window, paths: Iterable[str], title: str) -> bool:
    """Whether to go ahead when some of *paths* are already there and no
    save dialog has asked (files named for each page or part): Replace or
    Cancel. A test answers through ``window.replace_answer``."""
    there = [p for p in paths if os.path.exists(p)]
    if not there:
        return True
    names = ", ".join(os.path.basename(p) for p in there[:3]) + ("…" if len(there) > 3 else "")
    text = (f"{os.path.basename(there[0])} is already there. Replace it?" if len(there) == 1
            else f"{len(there)} of the files are already there ({names}). Replace them?")
    window.replace_said = text
    answer = getattr(window, "replace_answer", None)
    if answer is not None:
        return bool(answer(text) if callable(answer) else answer)
    if not getattr(window, "interactive_prompts", True):
        return False
    box = QMessageBox(QMessageBox.Question, title, text, QMessageBox.NoButton, window)
    replace = box.addButton("Replace", QMessageBox.AcceptRole)
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(replace)
    box.exec()
    return box.clickedButton() is replace


def tell(window, title: str, text: str) -> None:
    """Say why something can't be done, and wait for OK (a test reads
    ``window.told``; without prompts it is the status bar's only)."""
    told = window.__dict__.setdefault("told", [])
    told.append(text)
    status = getattr(window, "status_hint", None)
    if status is not None:
        status.setText(text)
    if getattr(window, "interactive_prompts", True) and \
            getattr(window, "save_as_answer", None) is None:
        QMessageBox.information(window, title, text)
