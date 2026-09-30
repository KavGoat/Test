"""How a saved page looks in CalcForge, and in two other PDF readers.

The same page drawn three ways — by CalcForge itself (what the reader sees on
screen, printed the way a save prints it), by MuPDF, and by pdfium (the engine
in Chrome and Foxit, reached through QtPdf) — compared a region at a time. A
reader that draws a markup differently from CalcForge is a markup that looks
wrong to whoever the file is sent to.
"""
from __future__ import annotations

import numpy as np
import pymupdf
from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QImage, QPainter

SCALE = 2.0             # pixels per point the pages are compared at
INK = 185               # darker than this (mean of R, G, B) is ink


def as_array(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format_RGB32)
    raw = np.frombuffer(image.constBits(), np.uint8).reshape(
        image.height(), image.bytesPerLine() // 4, 4)
    return raw[:, :image.width(), 2::-1].astype(np.int16)     # BGRA -> RGB


def calcforge(frame) -> np.ndarray:
    size = (int(frame.page.width_pt * SCALE), int(frame.page.height_pt * SCALE))
    image = QImage(size[0], size[1], QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    frame.render_page(painter, QRectF(0, 0, size[0], size[1]), for_print=True)
    painter.end()
    return as_array(image)


def mupdf(path: str, index: int) -> np.ndarray:
    with pymupdf.open(path) as document:
        pix = document[index].get_pixmap(matrix=pymupdf.Matrix(SCALE, SCALE),
                                         annots=True, alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(
        pix.height, pix.width, pix.n)[..., :3].astype(np.int16)


def pdfium(path: str, index: int) -> np.ndarray:
    from PySide6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions

    document = QPdfDocument()
    document.load(path)
    size = document.pagePointSize(index)
    options = QPdfDocumentRenderOptions()
    options.setRenderFlags(QPdfDocumentRenderOptions.RenderFlag.Annotations)
    image = document.render(index, QSize(round(size.width() * SCALE),
                                         round(size.height() * SCALE)), options)
    document.close()
    flat = QImage(image.size(), QImage.Format_RGB32)
    flat.fill(0xFFFFFFFF)
    painter = QPainter(flat)
    painter.drawImage(0, 0, image)
    painter.end()
    return as_array(flat)


def compare(a: np.ndarray, b: np.ndarray, box: QRectF) -> dict:
    """How alike two drawings of one region are.

    ``overlap`` — of the ink either one put down, the share both put down
    (within a pixel, so antialiasing differences don't count); ``shift`` —
    how far apart the edges of the ink are, in points; ``colour`` — the mean
    difference of the ink's average colour, 0–255.
    """
    x0, y0 = int(box.left() * SCALE), int(box.top() * SCALE)
    x1, y1 = int(box.right() * SCALE), int(box.bottom() * SCALE)
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    a, b = a[y0:min(y1, h), x0:min(x1, w)], b[y0:min(y1, h), x0:min(x1, w)]
    ia, ib = a.mean(axis=2) < INK, b.mean(axis=2) < INK
    if not ia.any() and not ib.any():
        return {"overlap": 1.0, "shift": 0.0, "colour": 0.0, "ink": (0, 0)}
    if not ia.any() or not ib.any():
        return {"overlap": 0.0, "shift": 99.0, "colour": 255.0,
                "ink": (int(ia.sum()), int(ib.sum()))}
    da, db = _grow(ia), _grow(ib)
    overlap = ((ia & db).sum() + (ib & da).sum()) / (ia.sum() + ib.sum())
    ya, xa = np.nonzero(ia)
    yb, xb = np.nonzero(ib)
    shift = max(abs(int(xa.min()) - int(xb.min())), abs(int(xa.max()) - int(xb.max())),
                abs(int(ya.min()) - int(yb.min())), abs(int(ya.max()) - int(yb.max()))) / SCALE
    # Each inked pixel against the nearest-coloured pixel within one pixel of
    # it in the other drawing, both ways: thin letters and lines placed a
    # fraction of a pixel apart match, several colours in one region are
    # each held to their own, and a wrong colour (units not blue, a fill
    # gone grey) shows.
    colour = max(_nearest_colour(a, b, ia), _nearest_colour(b, a, ib))
    return {"overlap": float(overlap), "shift": shift, "colour": colour,
            "ink": (int(ia.sum()), int(ib.sum()))}


def _nearest_colour(a: np.ndarray, b: np.ndarray, where: np.ndarray) -> float:
    best = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            moved = np.roll(np.roll(b, dy, axis=0), dx, axis=1)
            gap = np.abs(a - moved).max(axis=2)
            best = gap if best is None else np.minimum(best, gap)
    return float(best[where].mean())


def _shrink(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out &= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def _core(ink: np.ndarray) -> np.ndarray:
    darkness = ink.mean(axis=1)
    keep = darkness <= np.percentile(darkness, 25)
    return ink[keep].mean(axis=0)


def _grow(mask: np.ndarray, by: int = 2) -> np.ndarray:
    out = mask.copy()
    for dy in range(-by, by + 1):
        for dx in range(-by, by + 1):
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out
