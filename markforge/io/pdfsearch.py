"""Finding words in a PDF page's own text, in page coordinates.

MuPDF finds the words and says where they are, in the page's unrotated
space; the same turn and scale the vector reader uses puts each hit on the
page as it is shown here.
"""
from __future__ import annotations

import pymupdf

from ..pdf import engine


def find_on_page(data: bytes, index: int, needle: str, width_pt: float,
                 height_pt: float) -> list[tuple[tuple, str]]:
    """Every hit of *needle* on one page: ((x, y, w, h), words around it).

    Case is ignored, as MuPDF's search ignores it.
    """
    if not data or not needle.strip():
        return []
    try:
        document = engine.open_bytes(data)
    except Exception:                                  # noqa: BLE001
        return []
    try:
        if not 0 <= index < document.page_count:
            return []
        page = document[index]
        scale_x = width_pt / max(page.rect.width, 1e-6)
        scale_y = height_pt / max(page.rect.height, 1e-6)
        matrix = page.rotation_matrix * pymupdf.Matrix(scale_x, scale_y)
        found = []
        for hit in page.search_for(needle):
            box = pymupdf.Rect(hit) * matrix
            around = pymupdf.Rect(hit.x0 - 80, hit.y0 - 1, hit.x1 + 80, hit.y1 + 1)
            context = " ".join(page.get_textbox(around).split())
            found.append(((box.x0, box.y0, box.width, box.height),
                          context or needle))
        return found
    except Exception:                                  # noqa: BLE001
        engine.drain_messages()
        return []
    finally:
        engine.close(document)
