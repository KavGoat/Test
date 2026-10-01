"""Process-local PDF rendering. This module deliberately has no Qt imports.

PyMuPDF is not thread-safe. Each renderer owns its documents and display lists
in a separate process. Requests and image dimensions cross a pipe; pixels
use a fixed shared-memory buffer which Qt copies before the next render.
"""
from __future__ import annotations

from collections import OrderedDict
import os
import time

from ..pdf import engine

MAX_DOCUMENTS = 6
# Parsed pages are what make a re-render fast; keep plenty of them.
MAX_DISPLAY_LISTS = 24
# A sheet's markups, one parsed annotation each: small, so many more.
MAX_ANNOTATION_LISTS = 600


def worker_count() -> int:
    """Use every core but one, which is kept for the window and the OS."""
    available = getattr(os, 'process_cpu_count', os.cpu_count)() or 1
    default = min(8, max(1, available - 1))
    try:
        requested = int(os.environ.get('CALCFORGE_PDF_WORKERS', default))
    except ValueError:
        requested = default
    return max(1, min(requested, available, 8))


class Renderer:
    """An LRU of parsed pages, owned and accessed by exactly one process."""

    def __init__(self):
        self.documents = OrderedDict()
        self.drawings = OrderedDict()
        self.annotations = OrderedDict()          # (path, index, xref) -> display list
        self.emptied = set()                      # (path, index) emptied in the copy
        self.opens = 0
        self.parses = 0

    def close(self):
        self.drawings.clear()
        for document in self.documents.values():
            engine.close(document)
        self.documents.clear()

    def forget(self, path):
        for key in list(self.annotations):
            if key[0] == path:
                del self.annotations[key]
        self.emptied = {key for key in self.emptied if key[0] != path}
        for key in list(self.drawings):
            if key[0] == path:
                del self.drawings[key]
        for key in list(self.documents):
            if key[0] == path:
                engine.close(self.documents.pop(key))

    def render(self, path, index, annotations, without, region, scale):
        key = (path, index, annotations, without)
        drawing = self.drawings.get(key)
        if drawing is None:
            document_key = (path, without)
            document = self.documents.get(document_key)
            if document is None:
                if len(self.documents) >= MAX_DOCUMENTS:
                    oldest = next(iter(self.documents))
                    self.forget(oldest[0])
                document = engine.open_path(path)
                self.documents[document_key] = document
                self.opens += 1
            self.documents.move_to_end(document_key)
            drawing = engine.display_list(document, index, annotations, without)
            if drawing is None:
                return None
            self.drawings[key] = drawing
            self.parses += 1
            while len(self.drawings) > MAX_DISPLAY_LISTS:
                self.drawings.popitem(last=False)
        self.drawings.move_to_end(key)
        return engine.raster_from(drawing, region, scale)

    def render_annotation(self, path, index, xref, region, scale):
        """One of the page's markups alone, as its file draws it, on a clear
        background: the page is drawn without it, and the markup's own item
        lays this over the page until somebody changes it."""
        key = (path, index, xref)
        drawing = self.annotations.get(key)
        if drawing is None:
            document_key = (path, "annotations only")
            document = self.documents.get(document_key)
            if document is None:
                if len(self.documents) >= MAX_DOCUMENTS:
                    oldest = next(iter(self.documents))
                    self.forget(oldest[0])
                document = engine.open_path(path)
                self.documents[document_key] = document
                self.opens += 1
            self.documents.move_to_end(document_key)
            if (path, index) not in self.emptied:
                engine.without_page_content(document, index)
                self.emptied.add((path, index))
            drawing = engine.annotation_display_list(document, index, xref)
            if drawing is None:
                return None
            self.annotations[key] = drawing
            self.parses += 1
            while len(self.annotations) > MAX_ANNOTATION_LISTS:
                self.annotations.popitem(last=False)
        self.annotations.move_to_end(key)
        return engine.raster_from(drawing, region, scale, alpha=True)


def serve(connection, memory_name, memory_size):
    """One persistent renderer. The parent assigns at most one job at a time."""
    from multiprocessing.shared_memory import SharedMemory
    memory = SharedMemory(name=memory_name)
    renderer = Renderer()
    try:
        while True:
            request = connection.recv()
            if request is None:
                break
            if request[0] == 'forget':
                renderer.forget(request[1])
                continue
            started = time.perf_counter()
            try:
                if request[0] == 'annotation':
                    raster = renderer.render_annotation(*request[1:])
                else:
                    raster = renderer.render(*request[1:])
            except Exception:
                # A broken PDF does not poison the renderer for the next file.
                raster = None
            description = None
            if raster is not None and not raster.is_empty:
                size = len(raster.samples)
                if size <= memory_size:
                    memory.buf[:size] = raster.samples
                    description = (raster.width, raster.height, raster.stride, raster.alpha)
            connection.send((description, {
                'pid': os.getpid(), 'seconds': time.perf_counter() - started,
                'opens': renderer.opens, 'parses': renderer.parses,
            }))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        renderer.close()
        memory.close()
        connection.close()

