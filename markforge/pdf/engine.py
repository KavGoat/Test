"""The PDF engine: MuPDF.

Everything that touches a PDF as a *file* goes through here, and nothing here
imports Qt — the same split PDF4QT keeps between its rendering library and its
applications, and the one pdf4py keeps between its document model and its
window. Above this line a page is a rectangle of points with markups on it;
below it a page is objects, streams and a cross-reference table, and MuPDF is
what reads and writes them.

**Display points.** The coordinates handed in and out of this module are PDF
user-space points with the page's own ``/Rotate`` already applied: origin at
the top-left corner, y down, and a page that says it is turned ninety degrees
measures as the landscape sheet it is drawn as. That is what the rest of
MarkForge means by a page coordinate, so the conversion happens once, here,
rather than being got right in some places and forgotten in others.

MuPDF gives three matrices for this and the names are worth keeping straight:

* ``page.rotation_matrix`` turns unrotated page space into display space.
* ``page.derotation_matrix`` turns display space back into unrotated space.
* ``page.transformation_matrix`` turns unrotated page space into *PDF* space,
  which is the one measured from the bottom-left corner upwards — where an
  annotation's ``/Rect`` and a line's ``/L`` actually live.

So :func:`to_pdf` is display space to the file's own space, and
:func:`to_display` is the way back. Nothing above this module should be
composing matrices of its own.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import pymupdf

from .objects import Name, Ref, Stream

# MuPDF complains on stderr about every damaged file it repairs, and drawing
# review sets are full of them. The complaints are kept and handed back as
# text instead, so a window can say "this file was repaired" once rather than
# a terminal filling up with things nobody asked to see.
pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)


def drain_messages() -> str:
    """Whatever MuPDF has been complaining about, and a clean slate."""
    try:
        return pymupdf.TOOLS.mupdf_warnings(reset=True) or ""
    except Exception:                                  # noqa: BLE001
        return ""


class PdfError(RuntimeError):
    """A PDF could not be opened, read or written."""


#: Annotations that are the file's own furniture rather than somebody's markup.
NOT_MARKUP = {"Link", "Popup", "Widget", "FileAttachment", "Movie", "Screen",
              "PrinterMark", "TrapNet", "Watermark", "3D", "Projection"}

#: A4, for a page whose size cannot be had.
A4_POINTS = (595.28, 841.89)


@dataclass(frozen=True)
class Raster:
    """A rendered image, ready to be wrapped in a QImage.

    *x* and *y* are where the picture belongs, in pixels, when it is part of
    something bigger — a tile of a page, or one annotation's appearance.
    """

    samples: bytes
    width: int
    height: int
    stride: int
    alpha: bool
    x: int = 0
    y: int = 0

    @property
    def is_empty(self) -> bool:
        return self.width < 1 or self.height < 1 or not self.samples


# ---------------------------------------------------------------------------
# opening
# ---------------------------------------------------------------------------

#: How far into a file the ``%PDF`` header is still the header. It belongs at
#: the very front, but files that have had something prepended to them are
#: common enough — and readable enough — to be worth looking a little further.
HEADER_WITHIN = 1024


def looks_like_pdf(data: bytes) -> bool:
    """Whether these bytes are a PDF at all.

    Worth asking before MuPDF is, because MuPDF is not only a PDF library: told
    to open an HTML file as a PDF it will lay the HTML out and hand back a
    perfectly good one-page document. That is the right answer to a question
    nobody here is asking, and it turns "this is not a drawing" into a blank
    page that looks like a drawing that failed to load.
    """
    return b"%PDF" in bytes(data or b"")[:HEADER_WITHIN]


def open_bytes(data: bytes) -> "pymupdf.Document":
    """A PDF held in memory, opened. Raises :class:`PdfError` if it will not."""
    if not data:
        raise PdfError("There are no bytes to read as a PDF.")
    if not looks_like_pdf(data):
        raise PdfError("This is not a PDF.")
    drain_messages()
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
        pages = document.page_count
    except Exception as exc:                           # noqa: BLE001
        drain_messages()
        raise PdfError(f"Could not read this PDF: {exc}") from exc
    # MuPDF repairs rather than refuses, which is what makes a damaged drawing
    # openable at all — but it will also repair something that was never a PDF
    # into a document with nothing in it. A file with no pages is not a file
    # this read, whatever it managed to salvage.
    if pages < 1:
        close(document)
        drain_messages()
        raise PdfError("There are no pages in this PDF.")
    return document


def open_path(path: str) -> "pymupdf.Document":
    """The PDF at *path*, opened."""
    if not is_pdf(path):
        raise PdfError(f"{os.path.basename(path)} is not a PDF.")
    drain_messages()
    try:
        document = pymupdf.open(path, filetype="pdf")
    except Exception as exc:                           # noqa: BLE001
        drain_messages()
        raise PdfError(f"Could not open {path}: {exc}") from exc
    if document.needs_pass:
        document.close()
        raise PdfError(f"{os.path.basename(path)} is password protected.")
    return document


def is_pdf(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            return looks_like_pdf(handle.read(HEADER_WITHIN))
    except OSError:
        return False


def close(document: Optional["pymupdf.Document"]) -> None:
    """Shut a document, without minding if it is already shut."""
    if document is None:
        return
    try:
        document.close()
    except Exception:                                  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------

def page_size(document: "pymupdf.Document", index: int) -> tuple[float, float]:
    """One page's size in display points — its rotation already applied."""
    try:
        box = document[index].rect
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return A4_POINTS
    if box.width < 1 or box.height < 1:
        return A4_POINTS
    return float(box.width), float(box.height)


def page_rotation(document: "pymupdf.Document", index: int) -> int:
    try:
        return int(document[index].rotation) % 360
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return 0


def to_pdf(page: "pymupdf.Page") -> "pymupdf.Matrix":
    """Display points to the file's own space, where /Rect and /L are kept."""
    return page.derotation_matrix * page.transformation_matrix


def to_display(page: "pymupdf.Page") -> "pymupdf.Matrix":
    """The file's own space back to display points."""
    return ~pymupdf.Matrix(page.transformation_matrix) * page.rotation_matrix


def display_point(page: "pymupdf.Page", x: float, y: float) -> tuple[float, float]:
    point = pymupdf.Point(x, y) * to_display(page)
    return float(point.x), float(point.y)


def pdf_point(page: "pymupdf.Page", x: float, y: float) -> tuple[float, float]:
    point = pymupdf.Point(x, y) * to_pdf(page)
    return float(point.x), float(point.y)


def pdf_point_with(matrix: "pymupdf.Matrix", x: float,
                   y: float) -> tuple[float, float]:
    """One display point through a transform already worked out."""
    point = pymupdf.Point(float(x), float(y)) * matrix
    return float(point.x), float(point.y)


# ---------------------------------------------------------------------------
# drawing pages
# ---------------------------------------------------------------------------

def _raster_of(pixmap: "pymupdf.Pixmap") -> Optional[Raster]:
    if pixmap is None or not pixmap.width or not pixmap.height:
        return None
    box = pixmap.irect
    return Raster(bytes(pixmap.samples), pixmap.width, pixmap.height,
                  pixmap.stride, bool(pixmap.alpha),
                  int(box[0]), int(box[1]))


def render_page(document: "pymupdf.Document", index: int,
                width: int, height: int,
                annotations: bool = True) -> Optional[Raster]:
    """One whole page at an exact pixel size.

    The size is asked for in pixels rather than as a zoom because that is what
    a window has: a rectangle on screen to fill. The scale that gets there is
    worked out per axis, so a page asked for at an aspect ratio of its own is
    still drawn to fill exactly what was asked for.
    """
    width, height = max(int(width), 1), max(int(height), 1)
    try:
        page = document[index]
        box = page.rect
        matrix = pymupdf.Matrix(width / max(box.width, 1e-6),
                                height / max(box.height, 1e-6))
        pixmap = page.get_pixmap(matrix=matrix, annots=annotations)
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return None
    return _raster_of(pixmap)


def render_region(document: "pymupdf.Document", index: int,
                  region: tuple[float, float, float, float], scale: float,
                  annotations: bool = True) -> Optional[Raster]:
    """Part of a page, at *scale* pixels to the display point.

    *region* is in display points. Only the piece asked for is drawn — MuPDF
    clips before it rasterises — which is how a reader shows a detail of an A1
    sheet sharply without ever making a picture of the whole sheet at that
    size.
    """
    try:
        page = document[index]
        clip = pymupdf.Rect(*region).normalize() & page.rect
        if clip.is_empty:
            return None
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                 clip=clip, annots=annotations)
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return None
    return _raster_of(pixmap)


def display_list(document: "pymupdf.Document", index: int,
                 annotations: bool = True, without: "tuple" = ()):
    """A page parsed once, ready to be rasterised any number of times.

    Asking a page for a square of itself runs its whole content stream again,
    and a drawing sheet is tens of thousands of path operations — so a page cut
    into forty tiles is parsed forty times. Held as a display list it is parsed
    once and each tile after that is only rasterising.

    *without* names annotations by xref that this page must not draw, because
    something else is drawing them — a markup somebody has taken over, and one
    the file drew as well would show twice. **This changes the document**: the
    annotations are marked hidden, and the caller must not go on to use it for
    a page that wants them back. Give each set of left-out annotations its own
    copy of the document.
    """
    try:
        page = document[index]
        if without:
            leave_out(page, without)
        return page.get_displaylist(annots=annotations)
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return None


def annotation_raster(document: "pymupdf.Document", index: int, xref: int,
                      scale: float = 3.0) -> Optional[Raster]:
    """One annotation drawn the way its own file draws it.

    For the few markups there is nothing else to draw: a stamp is a picture
    and a logo and a ruled table, described nowhere but in its own appearance
    stream, and there is no dictionary to rebuild it from.
    """
    try:
        for annotation in document[index].annots():
            if annotation.xref != xref:
                continue
            pixmap = annotation.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                           alpha=True)
            if not pixmap.width or not pixmap.height:
                return None
            return Raster(pixmap.samples, pixmap.width, pixmap.height,
                          pixmap.stride, bool(pixmap.alpha))
    except Exception:                                  # noqa: BLE001
        drain_messages()
    return None


def leave_out(page, without: "tuple") -> None:
    """Mark the named annotations hidden, so nothing draws them."""
    wanted = set(without)
    if not wanted:
        return
    try:
        for annotation in page.annots():
            if annotation.xref in wanted:
                annotation.set_flags(annotation.flags
                                     | pymupdf.PDF_ANNOT_IS_HIDDEN)
    except Exception:                                  # noqa: BLE001
        drain_messages()


def raster_from(drawing, region: tuple[float, float, float, float],
                scale: float) -> Optional[Raster]:
    """Part of an already-parsed page, at *scale* pixels to the display point."""
    try:
        clip = pymupdf.Rect(*region).normalize()
        if clip.is_empty:
            return None
        pixmap = drawing.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                    clip=clip, alpha=False)
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return None
    return _raster_of(pixmap)


def render_thumbnail(document: "pymupdf.Document", index: int,
                     longest_edge: int = 140,
                     annotations: bool = True) -> Optional[Raster]:
    """A small picture of a whole page, its longest edge that many pixels."""
    width, height = page_size(document, index)
    shrink = max(longest_edge, 1) / max(width, height, 1.0)
    return render_page(document, index,
                       max(int(width * shrink), 1), max(int(height * shrink), 1),
                       annotations)


# ---------------------------------------------------------------------------
# reading objects
# ---------------------------------------------------------------------------

def object_at(document: "pymupdf.Document", number: int) -> Any:
    """One numbered object, as plain Python values.

    MuPDF hands an object back as the source text a PDF writes it in, and that
    is a shape MarkForge already reads: :mod:`markforge.io.pdfobj` parses it
    into dictionaries, lists, :class:`~markforge.pdf.objects.Name` and
    :class:`~markforge.pdf.objects.Ref`. Going through the text rather than
    through key-by-key accessors means a whole annotation arrives in one piece
    and reads exactly as it is written in the file.
    """
    from ..io.pdfobj import parse

    try:
        source = document.xref_object(number, compressed=True)
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return None
    if not source or source == "null":
        return None
    try:
        value, _at = parse(source.encode("latin-1", "replace"), 0, references=True)
    except Exception:                                  # noqa: BLE001
        return None
    return value


def stream_of(document: "pymupdf.Document", number: int) -> bytes:
    """A stream object's bytes, with its filters already undone."""
    try:
        return document.xref_stream(number) or b""
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return b""


def annotation_xrefs(document: "pymupdf.Document", index: int) -> list[int]:
    """The page's annotations, in the order the file keeps them.

    Order is what decides which markup is drawn over which, so it is read from
    the page's own ``/Annots`` array rather than from anything that might sort
    it.
    """
    try:
        page_number = document.page_xref(index)
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return []
    holder = object_at(document, page_number)
    if not isinstance(holder, dict):
        return []
    entries = holder.get("Annots")
    if isinstance(entries, Ref):
        entries = object_at(document, entries.number)
    if not isinstance(entries, (list, tuple)):
        return []
    return [entry.number for entry in entries if isinstance(entry, Ref)]


# ---------------------------------------------------------------------------
# writing objects
# ---------------------------------------------------------------------------

def serialize(value: Any) -> bytes:
    """One value, as a PDF writes it.

    The vocabulary is the one :mod:`markforge.pdf.objects` describes, so a
    markup's annotation is built once as plain dictionaries and names and
    written from that — rather than being built again in whatever object types
    some library happens to want.
    """
    if value is None:
        return b"null"
    if isinstance(value, Name):
        return b"/" + _escaped_name(str(value))
    if isinstance(value, Ref):
        return f"{value.number} {value.generation} R".encode("ascii")
    if isinstance(value, bool):
        return b"true" if value else b"false"
    if isinstance(value, int):
        return str(value).encode("ascii")
    if isinstance(value, float):
        return _real(value)
    if isinstance(value, bytes):
        return _hex_string(value)
    if isinstance(value, str):
        return _text_string(value)
    if isinstance(value, (list, tuple)):
        return b"[" + b" ".join(serialize(item) for item in value) + b"]"
    if isinstance(value, Stream):
        return serialize(value.dictionary)
    if isinstance(value, dict):
        body = b"".join(b"/" + _escaped_name(str(key)) + b" " + serialize(item)
                        for key, item in value.items())
        return b"<<" + body + b">>"
    raise PdfError(f"A {type(value).__name__} is not a PDF object.")


def _real(value: float) -> bytes:
    """A number, written the way a PDF wants it: no exponent, no trailing zeros."""
    if value != value or value in (float("inf"), float("-inf")):
        return b"0"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return (text or "0").encode("ascii")


def _escaped_name(text: str) -> bytes:
    out = bytearray()
    for byte in text.encode("utf-8"):
        if byte < 0x21 or byte > 0x7E or byte in b"()<>[]{}/%#":
            out += b"#%02X" % byte
        else:
            out.append(byte)
    return bytes(out)


def _text_string(text: str) -> bytes:
    """A string, in Latin-1 where it fits and UTF-16 where it does not.

    A markup written by somebody working in another language has to survive
    the round trip, and PDF's own single-byte encoding cannot carry it. The
    byte-order mark on the front is how a reader is told which one this is.
    """
    try:
        return _escaped_string(text.encode("latin-1"))
    except UnicodeEncodeError:
        return _hex_string(b"\xfe\xff" + text.encode("utf-16-be"))


def _escaped_string(raw: bytes) -> bytes:
    out = bytearray(b"(")
    for byte in raw:
        if byte in b"()\\":
            out += b"\\" + bytes([byte])
        elif byte == 0x0A:
            out += b"\\n"
        elif byte == 0x0D:
            out += b"\\r"
        elif byte < 0x20 or byte > 0x7E:
            out += b"\\%03o" % byte
        else:
            out.append(byte)
    out += b")"
    return bytes(out)


def _hex_string(raw: bytes) -> bytes:
    return b"<" + raw.hex().encode("ascii") + b">"


def add_object(document: "pymupdf.Document", value: Any) -> int:
    """Put *value* into the file as a new numbered object. Its number."""
    number = document.get_new_xref()
    document.update_object(number, serialize(value).decode("latin-1"))
    return number


def add_stream(document: "pymupdf.Document", dictionary: dict,
               data: bytes) -> int:
    """A new stream object: its dictionary, and the bytes it carries."""
    number = add_object(document, dictionary)
    document.update_stream(number, data, compress=1)
    return number


def set_page_annotations(document: "pymupdf.Document", index: int,
                         xrefs: list[int]) -> None:
    """Replace a page's annotation list with exactly these, in this order."""
    try:
        page_number = document.page_xref(index)
    except Exception as exc:                           # noqa: BLE001
        drain_messages()
        raise PdfError(f"Page {index + 1} could not be written to: {exc}") from exc
    if not xrefs:
        document.xref_set_key(page_number, "Annots", "null")
        return
    refs = " ".join(f"{number} 0 R" for number in xrefs)
    document.xref_set_key(page_number, "Annots", f"[{refs}]")


# ---------------------------------------------------------------------------
# appearances
# ---------------------------------------------------------------------------

def form_from_page(target: "pymupdf.Document", source: "pymupdf.Document",
                   index: int, width: float, height: float) -> Optional[int]:
    """One page of *source*, brought into *target* as a form XObject.

    This is how a markup drawn by Qt onto a scratch page becomes the
    appearance its annotation shows itself with. MuPDF already knows how to
    copy a page into another file as a form — resources, fonts and all,
    renumbered as it goes — so it is asked to, onto a page that is then thrown
    away. The form it made stays, because the annotation points at it.
    """
    if width <= 0 or height <= 0:
        return None
    try:
        holder = target.new_page(-1, width=width, height=height)
        holder.show_pdf_page(holder.rect, source, index)
        # Only the form placed directly on the page — MuPDF nests a second one
        # inside it, and pointing an annotation at the inner one would show
        # the drawing without whatever the outer one places it by.
        forms = [entry[0] for entry in holder.get_xobjects() if entry[2] == 0]
        target.delete_page(-1)
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return None
    return forms[0] if forms else None


def draws_something(document: "pymupdf.Document", index: int,
                    xref: int) -> bool:
    """Whether an annotation's appearance actually puts ink down.

    An appearance that draws nothing is worse than no appearance at all: the
    markup is in the file, and in the list, and invisible.
    """
    try:
        page = document[index]
        for annot in page.annots():
            if annot.xref != xref:
                continue
            pixmap = annot.get_pixmap(alpha=True)
            if not pixmap.width or not pixmap.height:
                return False
            samples, channels = pixmap.samples, pixmap.n
            return any(samples[at] for at in
                       range(channels - 1, len(samples), channels))
    except Exception:                                  # noqa: BLE001
        drain_messages()
    return False


# ---------------------------------------------------------------------------
# embedded files
# ---------------------------------------------------------------------------

def embed(document: "pymupdf.Document", name: str, data: bytes) -> None:
    """Attach *data* to the file under *name*, replacing an earlier copy.

    Saving twice must not leave two records, or reading one back would be a
    coin toss over which is current.
    """
    try:
        # Taken out and put back rather than updated in place: MuPDF's own
        # update refuses a plain bytes buffer, and an attachment that half
        # changed would be worse than either.
        if name in set(document.embfile_names()):
            document.embfile_del(name)
    except Exception:                                  # noqa: BLE001
        drain_messages()
    try:
        document.embfile_add(name, data, filename=name,
                             desc="MarkForge markup record")
    except Exception as exc:                           # noqa: BLE001
        drain_messages()
        raise PdfError(f"Could not attach {name}: {exc}") from exc


def embedded(document: "pymupdf.Document", name: str) -> Optional[bytes]:
    """What is attached under *name*, if anything is."""
    try:
        if name not in set(document.embfile_names()):
            return None
        return bytes(document.embfile_get(name))
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return None


# ---------------------------------------------------------------------------
# saving
# ---------------------------------------------------------------------------

def save_incremental(document: "pymupdf.Document", path: str) -> bool:
    """Append the changes to the file the document was opened from.

    Every original byte stays where it was; the changed objects, a new
    cross-reference and a new trailer go on the end. That is what a markup
    editor should do — the drawing that came in is still in the file exactly
    as its author wrote it — and it is the only way to add to a signed
    document without breaking the signature.

    False when it cannot be done that way, which is a file MuPDF had to repair
    on the way in: there are no original bytes left to leave alone.
    """
    try:
        document.save(path, incremental=True,
                      encryption=pymupdf.PDF_ENCRYPT_KEEP)
    except Exception:                                  # noqa: BLE001
        drain_messages()
        return False
    return True


def save_as(document: "pymupdf.Document", path: str,
            tidy: bool = True, also: "tuple" = ()) -> None:
    """Write the whole document out, atomically, through a temporary beside it.

    A save interrupted half way through must leave the drawing that was there,
    not half of a new one.

    **Everything given here is closed before the file is put in place**, and
    that is the point of *also* rather than an afterthought. Most of these
    saves are over the very file the document was read from — an export having
    its markups added, an outline written onto a finished PDF — and Windows
    will not let a file be replaced while anything still has it open. It fails
    with a permission error, the drawing is not saved, and what is left beside
    it is a ``.markforge-part`` file nobody asked for. Unix allows the rename
    and hides the whole thing, which is why it can sit there for a while.

    So the documents are finished with here, in order, and the caller must not
    use them again.
    """
    temporary = path + ".markforge-part"
    try:
        document.save(temporary, garbage=3 if tidy else 0,
                      deflate=True, clean=False)
    except Exception as exc:                           # noqa: BLE001
        drain_messages()
        _discard(temporary)
        raise PdfError(f"Could not write {path}: {exc}") from exc
    close(document)
    for held in also:
        close(held)
    try:
        os.replace(temporary, path)
    except OSError as exc:
        _discard(temporary)
        raise PdfError(f"Could not write {path}: {exc}") from exc


def _discard(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def to_bytes(document: "pymupdf.Document", tidy: bool = True) -> bytes:
    try:
        return document.tobytes(garbage=3 if tidy else 0, deflate=True)
    except Exception as exc:                           # noqa: BLE001
        drain_messages()
        raise PdfError(f"Could not write this PDF: {exc}") from exc
