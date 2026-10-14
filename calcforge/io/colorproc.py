"""Bluebeam's Color Processing (Document ▸ Color Processing), on a page's PDF
itself, on a snapshot's drawing and on a photo.

Six process types, as Bluebeam has them:

* Modify Colors — each source colour (within a tolerance) becomes another,
  or no colour at all; vector content only, the current page only;
* Colorize — every colour onto one scale, the darkest to the Select colour,
  the lightest to the To colour (with Scale Color cleared, all onto the
  Select colour; the paper's white is kept, so black gives a black-and-white
  drawing);
* Grayscale; Black and White (the paper's white kept);
* Luminosity, Saturation and Hue;
* Mask Images — one colour in the images made transparent.

On a PDF page the colours are changed where the page sets them — the
colour operators of its content and of the forms it draws — so the page
stays vector line work, prints as it did and stays sharp at any zoom; its
images change too when Process Images is ticked (always, for Mask Images).
A photo has Colorize and Mask only, as in Bluebeam.
"""
from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

MODIFY, COLORIZE, GRAYSCALE, BLACK_WHITE, LSH, MASK = (
    "modify", "colorize", "grayscale", "bw", "lsh", "mask")
NAMES = {MODIFY: "Modify Colors", COLORIZE: "Colorize", GRAYSCALE: "Grayscale",
         BLACK_WHITE: "Black and White", LSH: "Luminosity, Saturation, and Hue",
         MASK: "Mask Images"}
WHITE_LEVEL = 0.98          # this light or lighter is the paper, and stays white

RGB = tuple   # (r, g, b), each 0..1


@dataclass
class Process:
    kind: str = MODIFY
    pairs: list = field(default_factory=lambda: [("#000000", "#ff0000")])  # (from, to or None)
    tolerance: int = 0                   # percent
    select: str = "#000000"              # Colorize: the darkest go to this
    to: str = "#ffffff"                  # and the lightest to this
    scale: bool = True                   # cleared: everything onto Select
    images: bool = False                 # Process Images
    luminosity: int = 0                  # -100..100
    saturation: int = 0                  # -100..100
    hue: int = 0                         # -180..180 degrees
    mask: str = "#ffffff"                # Mask Images: this colour made transparent

    def acts_on_vectors(self) -> bool:
        return self.kind != MASK

    def acts_on_images(self) -> bool:
        return self.kind == MASK or (self.images and self.kind != MODIFY)


def _rgb(hex_colour: str) -> RGB:
    text = hex_colour.lstrip("#")
    return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def hex_of(rgb: RGB) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02x}" for v in rgb)


def _luma(rgb: RGB) -> float:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def colour_function(proc: Process) -> Callable[[RGB], Optional[RGB]]:
    """What a vector colour becomes: a colour, or None for no colour."""
    if proc.kind == MODIFY:
        pairs = [(_rgb(a), None if b is None else _rgb(b)) for a, b in proc.pairs]
        tol = max(0.0, proc.tolerance) / 100.0 + 1e-6

        def modify(rgb):
            for source, target in pairs:
                if max(abs(x - y) for x, y in zip(rgb, source)) <= tol:
                    return target
            return rgb
        return modify
    if proc.kind == COLORIZE:
        dark, light = _rgb(proc.select), _rgb(proc.to)

        def colorize(rgb):
            level = _luma(rgb)
            if not proc.scale:
                return (1.0, 1.0, 1.0) if level >= WHITE_LEVEL else dark
            return tuple(d + (l_ - d) * level for d, l_ in zip(dark, light))
        return colorize
    if proc.kind == GRAYSCALE:
        return lambda rgb: (_luma(rgb),) * 3
    if proc.kind == BLACK_WHITE:
        return lambda rgb: (1.0, 1.0, 1.0) if _luma(rgb) >= WHITE_LEVEL else (0.0, 0.0, 0.0)
    if proc.kind == LSH:
        def adjust(rgb):
            h, l_, s = colorsys.rgb_to_hls(*rgb)
            lum, sat = proc.luminosity / 100.0, proc.saturation / 100.0
            l_ = l_ + (1 - l_) * lum if lum >= 0 else l_ * (1 + lum)
            s = s + (1 - s) * sat if sat >= 0 else s * (1 + sat)
            h = (h + proc.hue / 360.0) % 1.0
            return colorsys.hls_to_rgb(h, max(0.0, min(1.0, l_)), max(0.0, min(1.0, s)))
        return adjust
    return lambda rgb: rgb


# -- pictures -------------------------------------------------------------------------------
def process_pixels(rgba, proc: Process):
    """An H×W×4 uint8 array (RGBA), processed — numpy, a whole image at once."""
    import numpy as np
    out = rgba.copy()
    rgb = out[..., :3].astype(np.float32) / 255.0
    luma = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    if proc.kind == MASK:
        target = np.array(_rgb(proc.mask), dtype=np.float32)
        tol = max(0.0, proc.tolerance) / 100.0 + 1e-6
        near = np.abs(rgb - target).max(axis=2) <= tol
        out[..., 3][near] = 0
        return out
    if proc.kind == MODIFY:
        new = rgb.copy()
        alpha = out[..., 3].copy()
        tol = max(0.0, proc.tolerance) / 100.0 + 1e-6
        done = np.zeros(luma.shape, bool)
        for source, target in proc.pairs:
            near = (np.abs(rgb - np.array(_rgb(source), dtype=np.float32)).max(axis=2) <= tol) & ~done
            if target is None:
                alpha[near] = 0
            else:
                new[near] = np.array(_rgb(target), dtype=np.float32)
            done |= near
        out[..., 3] = alpha
    elif proc.kind == COLORIZE:
        dark = np.array(_rgb(proc.select), dtype=np.float32)
        if proc.scale:
            light = np.array(_rgb(proc.to), dtype=np.float32)
            new = dark + (light - dark) * luma[..., None]
        else:
            new = np.where((luma >= WHITE_LEVEL)[..., None], 1.0, dark)
    elif proc.kind == GRAYSCALE:
        new = np.repeat(luma[..., None], 3, axis=2)
    elif proc.kind == BLACK_WHITE:
        new = np.repeat(np.where(luma >= 0.5, 1.0, 0.0)[..., None], 3, axis=2)
    else:                                   # LSH: per distinct colour, then mapped
        fn = colour_function(proc)
        flat = out[..., :3].reshape(-1, 3)
        keys, inverse = np.unique(flat, axis=0, return_inverse=True)
        mapped = np.array([fn(tuple(k / 255.0)) for k in keys], dtype=np.float32)
        new = mapped[inverse.reshape(-1)].reshape(rgb.shape)
    out[..., :3] = np.clip(np.round(new * 255.0), 0, 255).astype(np.uint8)
    return out


def process_qimage(image, proc: Process):
    """A QImage processed (a photo, a scanned page, a picture in a snapshot)."""
    import numpy as np
    from PySide6.QtGui import QImage
    source = image.convertToFormat(QImage.Format_RGBA8888)
    width, height = source.width(), source.height()
    if width == 0 or height == 0:
        return QImage(source)
    stride = source.bytesPerLine()
    raw = np.frombuffer(source.constBits(), np.uint8, count=stride * height).reshape(height, stride)
    rgba = raw[:, :width * 4].reshape(height, width, 4)
    done = np.ascontiguousarray(process_pixels(rgba, proc))
    out = QImage(done.data, width, height, width * 4, QImage.Format_RGBA8888)
    return out.copy()


# -- a PDF page's own colours -----------------------------------------------------------------
_WS = b" \t\r\n\x0c\x00"
_DELIM = b"()<>[]{}/%"
_NUMBER = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)")
_DEVICE = {b"DeviceGray": 1, b"DeviceRGB": 3, b"DeviceCMYK": 4, b"G": 1, b"RGB": 3, b"CMYK": 4}
_FILL_PAINT = {b"f", b"F", b"f*"}
_BOTH_PAINT = {b"B", b"B*", b"b", b"b*"}


def _tokens(data: bytes):
    """(start, end, kind, value): kind is "num", "name", "op", or "other".
    Strings, arrays, dictionaries and comments come out as "other"; an
    inline image (BI … ID … EI) as one "other" token."""
    i, n = 0, len(data)
    while i < n:
        c = data[i:i + 1]
        if c in (b" ", b"\t", b"\r", b"\n", b"\x0c", b"\x00"):
            i += 1
            continue
        if c == b"%":
            j = data.find(b"\n", i)
            j = n if j < 0 else j
            yield i, j, "other", None
            i = j
            continue
        if c == b"(":
            depth, j = 1, i + 1
            while j < n and depth:
                ch = data[j:j + 1]
                if ch == b"\\":
                    j += 2
                    continue
                if ch == b"(":
                    depth += 1
                elif ch == b")":
                    depth -= 1
                j += 1
            yield i, j, "other", None
            i = j
            continue
        if c == b"<":
            if data[i + 1:i + 2] == b"<":
                yield i, i + 2, "other", None
                i += 2
                continue
            j = data.find(b">", i)
            j = n if j < 0 else j + 1
            yield i, j, "other", None
            i = j
            continue
        if c == b">" and data[i + 1:i + 2] == b">":
            yield i, i + 2, "other", None
            i += 2
            continue
        if c in (b"[", b"]", b"{", b"}", b">"):
            yield i, i + 1, "other", None
            i += 1
            continue
        if c == b"/":
            j = i + 1
            while j < n and data[j:j + 1] not in (b" ", b"\t", b"\r", b"\n", b"\x0c", b"\x00") \
                    and data[j:j + 1] not in _DELIM_SET:
                j += 1
            yield i, j, "name", data[i + 1:j]
            i = j
            continue
        m = _NUMBER.match(data, i)
        if m and m.end() > i:
            yield i, m.end(), "num", float(m.group(0))
            i = m.end()
            continue
        j = i
        while j < n and data[j:j + 1] not in (b" ", b"\t", b"\r", b"\n", b"\x0c", b"\x00") \
                and data[j:j + 1] not in _DELIM_SET:
            j += 1
        if j == i:
            j = i + 1
        word = data[i:j]
        if word == b"BI":
            k = data.find(b"ID", j)
            k = n if k < 0 else k + 2
            # the image data runs to an EI standing on its own
            end = k
            while True:
                e = data.find(b"EI", end)
                if e < 0:
                    end = n
                    break
                before = data[e - 1:e]
                after = data[e + 2:e + 3]
                if before in (b" ", b"\t", b"\r", b"\n", b"\x0c", b"\x00") and \
                        (after == b"" or after in (b" ", b"\t", b"\r", b"\n", b"\x0c", b"\x00")):
                    end = e + 2
                    break
                end = e + 2
            yield i, end, "other", None
            i = end
            continue
        yield i, j, "op", word
        i = j


_DELIM_SET = {bytes([c]) for c in _DELIM}


def _cmyk_to_rgb(c, m, y, k) -> RGB:
    return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))


def _fmt(v: float) -> bytes:
    text = f"{v:.4f}".rstrip("0").rstrip(".")
    return (text or "0").encode()


def rewrite_stream(data: bytes, spaces: dict, fn, seen: Optional[set] = None) -> bytes:
    """A content stream with every colour it sets put through *fn*.

    Everything else is kept byte for byte. *spaces* maps a resource colour
    space name to its number of components (None when it is not a plain
    gray/RGB/CMYK one: a pattern, a separation, an indexed space — those are
    left alone). Colours are noted in *seen* (hex) when given.
    """
    out = []
    last = 0
    operands: list = []
    # a stream starts in DeviceGray (PDF's initial colour space)
    state = {"fill": 1, "stroke": 1, "fill_none": False, "stroke_none": False}
    stack = []

    def colour_of(values, comps) -> Optional[RGB]:
        if comps == 1 and len(values) == 1:
            return (values[0],) * 3
        if comps == 3 and len(values) == 3:
            return tuple(values)
        if comps == 4 and len(values) == 4:
            return _cmyk_to_rgb(*values)
        return None

    def replace(start, end, text: bytes):
        nonlocal last
        out.append(data[last:start])
        out.append(text)
        last = end

    for start, end, kind, value in _tokens(data):
        if kind != "op":
            operands.append((start, end, kind, value))
            continue
        op = value
        if op == b"q":
            stack.append(dict(state))
        elif op == b"Q":
            if stack:
                state = stack.pop()
        elif op in (b"cs", b"CS"):
            name = operands[-1][3] if operands and operands[-1][2] == "name" else None
            comps = _DEVICE.get(name) if name in _DEVICE else spaces.get(name.decode("latin-1")) \
                if name is not None else None
            state["fill" if op == b"cs" else "stroke"] = comps
        elif op in (b"g", b"G", b"rg", b"RG", b"k", b"K", b"sc", b"SC", b"scn", b"SCN"):
            stroke = op in (b"G", b"RG", b"K", b"SC", b"SCN")
            nums = [o for o in operands if o[2] == "num"]
            names = [o for o in operands if o[2] == "name"]
            if op in (b"g", b"G"):
                comps = 1
            elif op in (b"rg", b"RG"):
                comps = 3
            elif op in (b"k", b"K"):
                comps = 4
            else:
                comps = state["stroke" if stroke else "fill"]
            colour = None if names else colour_of([o[3] for o in nums], comps)
            if colour is not None and operands:
                if seen is not None:
                    seen.add(hex_of(colour))
                new = fn(colour)
                key = "stroke_none" if stroke else "fill_none"
                if new is not None and max(abs(a - b) for a, b in zip(new, colour)) < 1e-9:
                    # left as it is: kept byte for byte (a CMYK colour stays CMYK)
                    state[key] = False
                elif new is None:
                    state[key] = True
                    replace(operands[0][0], end, b"")
                else:
                    state[key] = False
                    text = b" ".join(_fmt(v) for v in new) + (b" RG" if stroke else b" rg")
                    replace(operands[0][0], end, text)
                    if op in (b"sc", b"SC", b"scn", b"SCN", b"g", b"G", b"k", b"K"):
                        state["stroke" if stroke else "fill"] = 3
        elif op in _FILL_PAINT and state["fill_none"]:
            replace(start, end, b"n")
        elif op == b"S" and state["stroke_none"]:
            replace(start, end, b"n")
        elif op == b"s" and state["stroke_none"]:
            replace(start, end, b"h n")
        elif op in _BOTH_PAINT and (state["fill_none"] or state["stroke_none"]):
            closes = op in (b"b", b"b*")
            if state["fill_none"] and state["stroke_none"]:
                new = b"h n" if closes else b"n"
            elif state["fill_none"]:
                new = b"s" if closes else b"S"
            else:
                new = (b"h " if closes else b"") + (b"f*" if op.endswith(b"*") else b"f")
            replace(start, end, new)
        operands = []
    out.append(data[last:])
    return b"".join(out)


def _colour_spaces(doc, xref: int) -> dict:
    """{resource name: components} of the colour spaces an object's resources name."""
    out = {}
    try:
        kind, value = doc.xref_get_key(xref, "Resources/ColorSpace")
    except Exception:  # noqa: BLE001
        return out
    if kind == "xref":
        value = doc.xref_object(int(value.split()[0]))
        kind = "dict"
    if kind != "dict":
        return out
    for name, rest in re.findall(r"/([^\s/<>\[\]()]+)\s*(\[[^\]]*\]|\d+ 0 R|/\w+)", value):
        spec = rest
        if rest.endswith("R"):
            spec = doc.xref_object(int(rest.split()[0])).strip()
        comps = None
        for device, n in (("DeviceGray", 1), ("DeviceRGB", 3), ("DeviceCMYK", 4),
                          ("CalGray", 1), ("CalRGB", 3)):
            if spec.startswith("/" + device) or spec.startswith("[/" + device) or \
                    spec.startswith("[ /" + device):
                comps = n
        m = re.match(r"\[\s*/ICCBased\s+(\d+)\s+0\s+R", spec)
        if m:
            try:
                _k, n = doc.xref_get_key(int(m.group(1)), "N")
                comps = int(n) if n.isdigit() else None
            except Exception:  # noqa: BLE001
                comps = None
        out[name] = comps
    return out


def _page_streams(doc, page):
    xrefs = page.get_contents()
    return xrefs, b"\n".join(doc.xref_stream(x) or b"" for x in xrefs)


def process_pdf(data: bytes, indexes, proc: Process) -> bytes:
    """The PDF with the pages *indexes* (0-based) processed; the others as
    they were. A new file — the old one is left for undo."""
    import pymupdf
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        fn = colour_function(proc)
        done_forms: set = set()
        done_images: set = set()
        for index in indexes:
            page = doc[index]
            page_spaces = _colour_spaces(doc, page.xref)
            if proc.acts_on_vectors():
                xrefs, content = _page_streams(doc, page)
                if xrefs:
                    # the page starts in black: said, so black can be changed too
                    new = rewrite_stream(b"0 g 0 G\n" + content, page_spaces, fn)
                    doc.update_stream(xrefs[0], new)
                    for x in xrefs[1:]:
                        doc.update_stream(x, b"")
                for form in page.get_xobjects():
                    xref = form[0]
                    if xref in done_forms:
                        continue
                    done_forms.add(xref)
                    spaces = dict(page_spaces)
                    spaces.update(_colour_spaces(doc, xref))
                    stream = doc.xref_stream(xref)
                    if stream:
                        doc.update_stream(xref, rewrite_stream(stream, spaces, fn))
            if proc.acts_on_images():
                for image in page.get_images(full=True):
                    xref, smask = image[0], image[1]
                    if xref in done_images:
                        continue
                    done_images.add(xref)
                    _process_image(doc, page, xref, smask, proc)
        return doc.tobytes(garbage=1, deflate=True)
    finally:
        doc.close()


def _process_image(doc, page, xref: int, smask: int, proc: Process) -> None:
    import numpy as np
    import pymupdf
    try:
        pix = pymupdf.Pixmap(doc, xref)
    except Exception:  # noqa: BLE001
        return
    if pix.colorspace is None:                     # a stencil mask: no colours of its own
        return
    if smask:
        try:
            pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, smask))
        except Exception:  # noqa: BLE001
            pass
    if pix.colorspace.n != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    if not pix.alpha:
        pix = pymupdf.Pixmap(pix, 1)               # an alpha channel, all opaque
    rgba = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 4)
    done = process_pixels(rgba, proc)
    if np.array_equal(done, rgba):
        return
    new = pymupdf.Pixmap(pymupdf.csRGB, pix.width, pix.height, done.tobytes(), True)
    if not (done[..., 3] < 255).any():
        new = pymupdf.Pixmap(new, 0)               # no transparency: no mask
    page.replace_image(xref, pixmap=new)


def colours_in_pdf(data: bytes, index: int) -> list:
    """The colours a page's own content sets, most used first — Modify
    Colors' Source Color list ("only colors present in the PDF")."""
    import pymupdf
    seen: set = set()
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        page = doc[index]
        spaces = _colour_spaces(doc, page.xref)
        _xrefs, content = _page_streams(doc, page)
        rewrite_stream(b"0 g 0 G\n" + content, spaces, lambda c: c, seen)
        for form in page.get_xobjects():
            stream = doc.xref_stream(form[0])
            if stream:
                rewrite_stream(stream, {**spaces, **_colour_spaces(doc, form[0])}, lambda c: c, seen)
    finally:
        doc.close()
    return sorted(seen)


# -- markups (a snapshot's drawing, a page's own line work) ------------------------------------
def process_items(items, proc: Process) -> int:
    """Each markup's colours through the process; how many changed."""
    fn = colour_function(proc)

    def mapped(hex_colour: str) -> Optional[str]:
        if not hex_colour or not hex_colour.startswith("#") or len(hex_colour) < 7:
            return hex_colour
        new = fn(_rgb(hex_colour[:7]))
        return "" if new is None else hex_of(new)

    changed = 0
    for item in items:
        if hasattr(item, "process_colours"):
            changed += item.process_colours(mapped if proc.acts_on_vectors() else None,
                                            (lambda image: process_qimage(image, proc))
                                            if proc.acts_on_images() else None)
            continue
        style = getattr(item, "style", None)
        if style is None or not proc.acts_on_vectors():
            continue
        # only the colours the markup shows: its text colour if it holds
        # words, its hatch colour if it is hatched
        names = ["stroke", "fill"]
        if getattr(item, "text", None) or hasattr(item, "document_html"):
            names.append("text_color")
        if getattr(style, "hatch", ""):
            names.append("hatch_color")
        touched = False
        for name in names:
            old = getattr(style, name, "")
            new = mapped(old) if old else old
            if new != old:
                setattr(style, name, new)
                touched = True
        if touched:
            changed += 1
            item.update()
    return changed
