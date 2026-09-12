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

MAX_DOCUMENTS = 3
MAX_DISPLAY_LISTS = 6


def worker_count() -> int:
    """Use several cores while reserving CPU capacity for the window and OS."""
    available = getattr(os, 'process_cpu_count', os.cpu_count)() or 1
    default = min(4, max(1, available - 1))
    try:
        requested = int(os.environ.get('MARKFORGE_PDF_WORKERS', default))
    except ValueError:
        requested = default
    return max(1, min(requested, available, 8))


class Renderer:
    """An LRU of parsed pages, owned and accessed by exactly one process."""

    def __init__(self):
        self.documents = OrderedDict()
        self.drawings = OrderedDict()
        self.opens = 0
        self.parses = 0

    def close(self):
        self.drawings.clear()
        for document in self.documents.values():
            engine.close(document)
        self.documents.clear()

    def forget(self, path):
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
