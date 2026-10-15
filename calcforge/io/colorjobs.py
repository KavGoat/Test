"""Color Processing's heavy work, off the window's thread.

A large drawing's page took seconds to process, and the preview did it again
at every change — the window stopped answering, and on Windows that reads as
a crash (the user, 2026-10-15). The work goes to one helper process, kept for
the session; the window waits for it with a progress note, still drawing and
taking clicks, and a preview that has been overtaken is dropped.

Without a helper (one that will not start, or has died) the work is done
here, as before.
"""
from __future__ import annotations

from concurrent.futures import Future
from typing import Optional

from . import colorproc

_POOL = None


def _start() -> None:
    """In the helper: end with the application."""
    from .pdfrender import _die_with_parent
    _die_with_parent()


def pool():
    global _POOL
    if _POOL is None:
        try:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor
            _POOL = ProcessPoolExecutor(max_workers=1,
                                        mp_context=multiprocessing.get_context("spawn"),
                                        initializer=_start)
            import atexit
            atexit.register(shutdown)
        except Exception:  # noqa: BLE001
            _POOL = False
    return _POOL or None


def submit(fn, *args) -> Future:
    """*fn(*args)* in the helper; done here at once if there is none."""
    executor = pool()
    if executor is not None:
        try:
            return executor.submit(fn, *args)
        except Exception:  # noqa: BLE001 - a broken pool
            global _POOL
            _POOL = None
    future: Future = Future()
    try:
        future.set_result(fn(*args))
    except Exception as exc:  # noqa: BLE001
        future.set_exception(exc)
    return future


def result(future: Future, fn=None, *args):
    """The answer; a helper that died is replaced by doing it here."""
    try:
        return future.result()
    except Exception as exc:  # noqa: BLE001
        from concurrent.futures.process import BrokenProcessPool
        if isinstance(exc, BrokenProcessPool) and fn is not None:
            global _POOL
            _POOL = None
            return fn(*args)
        raise


# -- the jobs (plain functions, so the helper can run them) ------------------------------------
def render(data: bytes, index: int, size: int = 200):
    """(width, height, stride, RGB bytes) of a page drawn *size* across."""
    import pymupdf
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        page = doc[index]
        zoom = size / max(page.rect.width, page.rect.height, 1.0)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pix.width, pix.height, pix.stride, bytes(pix.samples)
    finally:
        doc.close()


def preview(single: bytes, proc: colorproc.Process, size: int = 200):
    """A one-page PDF processed and drawn small."""
    return render(colorproc.process_pdf(single, [0], proc), 0, size)


def process(data: bytes, indexes, proc: colorproc.Process) -> bytes:
    return colorproc.process_pdf(data, indexes, proc)


def colours(data: bytes, index: int) -> list:
    return colorproc.colours_in_pdf(data, index)


def shutdown() -> None:
    global _POOL
    if _POOL:
        _POOL.shutdown(wait=True, cancel_futures=True)
    _POOL = None


def wait(future: Future, parent=None, text: str = "Working…", fn=None, *args) -> Optional[object]:
    """Keep the window alive until *future* is done — after half a second, a
    progress note says so — then its result."""
    import time
    from PySide6.QtCore import QEventLoop, Qt
    from PySide6.QtWidgets import QApplication, QProgressDialog
    started = time.monotonic()
    note = None
    app = QApplication.instance()
    while not future.done():
        if note is None and time.monotonic() - started > 0.5 and app is not None:
            note = QProgressDialog(text, None, 0, 0, parent)
            note.setWindowTitle("Color Processing")
            note.setWindowModality(Qt.ApplicationModal)
            note.setMinimumDuration(0)
            note.show()
        if app is not None:
            app.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.01)
    if note is not None:
        note.close()
        note.deleteLater()
    return result(future, fn, *args)
