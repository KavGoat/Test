"""Windows metafiles (WMF and EMF), drawn as pictures.

Excel workbooks often carry their logos and diagrams as metafiles — a
company logo pasted from Word is one — and nothing on this side of Windows
reads them: openpyxl drops them, and Qt has no reader (the user, 2026-10-24:
"photos etc did not work" in 200PFC_WP30NC.xlsx, whose logo is a WMF). Here
the drawing commands they hold are played into a QPainter: lines, polygons,
rectangles, ellipses, text, and the bitmaps some of them wrap — what logos
and diagrams are made of. Anything else is passed over.

    picture(data, width_pt, height_pt) -> QImage or None
"""
from __future__ import annotations

import struct
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen,
                           QPolygonF, QTransform)

WMF_PLACEABLE = 0x9AC6CDD7
EMF_SIGNATURE = 0x464D4520          # " EMF"


def kind_of(data: bytes) -> str:
    """"wmf", "emf" or "" for bytes that are neither."""
    if len(data) >= 4 and struct.unpack_from("<I", data, 0)[0] == WMF_PLACEABLE:
        return "wmf"
    if len(data) >= 44 and struct.unpack_from("<I", data, 0)[0] == 1 \
            and struct.unpack_from("<I", data, 40)[0] == EMF_SIGNATURE:
        return "emf"
    if len(data) >= 18 and struct.unpack_from("<H", data, 0)[0] in (1, 2) \
            and struct.unpack_from("<H", data, 2)[0] == 9:
        return "wmf"                     # a WMF without its placeable header
    return ""


def picture(data: bytes, width_pt: float = 0.0, height_pt: float = 0.0,
            scale: float = 4.0) -> Optional[QImage]:
    """The metafile drawn on a transparent image *scale* pixels a point (at
    *width_pt* × *height_pt* when given, else its own size); None when it
    can't be read."""
    kind = kind_of(data)
    try:
        if kind == "wmf":
            return _Wmf(data).draw(width_pt, height_pt, scale)
        if kind == "emf":
            return _Emf(data).draw(width_pt, height_pt, scale)
    except (struct.error, ValueError, ZeroDivisionError, IndexError):
        return None
    return None


def png(data: bytes, width_pt: float = 0.0, height_pt: float = 0.0) -> Optional[bytes]:
    """The metafile as PNG bytes, or None."""
    image = picture(data, width_pt, height_pt)
    if image is None or image.isNull():
        return None
    return encoded(image)


def encoded(image: QImage) -> bytes:
    """*image* as PNG bytes."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    held = QByteArray()
    buffer = QBuffer(held)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(held)


# -- what both kinds share ------------------------------------------------------------------
def _colour(ref: int) -> QColor:
    """A COLORREF, 0x00BBGGRR."""
    return QColor(ref & 0xFF, (ref >> 8) & 0xFF, (ref >> 16) & 0xFF)


_HATCHES = {0: Qt.HorPattern, 1: Qt.VerPattern, 2: Qt.FDiagPattern, 3: Qt.BDiagPattern,
            4: Qt.CrossPattern, 5: Qt.DiagCrossPattern}
_DASHES = {1: Qt.DashLine, 2: Qt.DotLine, 3: Qt.DashDotLine, 4: Qt.DashDotDotLine}


def _pen(style: int, width: float, colour: int) -> Optional[QPen]:
    if style & 0x0F == 5:                # PS_NULL
        return None
    pen = QPen(_colour(colour))
    pen.setWidthF(max(0.0, width))
    pen.setCosmetic(width <= 1)
    pen.setStyle(_DASHES.get(style & 0x0F, Qt.SolidLine))
    pen.setJoinStyle(Qt.MiterJoin)
    return pen


def _brush(style: int, colour: int, hatch: int) -> Optional[QBrush]:
    if style == 1:                       # BS_NULL
        return None
    if style == 2:
        return QBrush(_colour(colour), _HATCHES.get(hatch, Qt.SolidPattern))
    return QBrush(_colour(colour))


def _dib(data: bytes) -> Optional[QImage]:
    """A device-independent bitmap (as in a metafile record) as an image."""
    if len(data) < 40:
        return None
    header = struct.unpack_from("<I", data, 0)[0]
    bits = struct.unpack_from("<H", data, 14)[0] if header >= 40 else 24
    colours = struct.unpack_from("<I", data, 32)[0] if header >= 40 else 0
    if not colours and bits <= 8:
        colours = 1 << bits
    offset = 14 + header + 4 * colours
    file = b"BM" + struct.pack("<IHHI", 14 + len(data), 0, 0, offset) + data
    image = QImage.fromData(file, "BMP")
    return None if image.isNull() else image


class _State:
    def __init__(self):
        self.pen = QPen(QColor("black"))
        self.pen.setCosmetic(True)
        self.brush: Optional[QBrush] = QBrush(QColor("white"))
        self.font = QFont("Arial")
        self.text_colour = QColor("black")
        self.fill_rule = Qt.OddEvenFill
        self.position = QPointF(0, 0)
        self.window_org = QPointF(0, 0)
        self.window_ext: Optional[tuple] = None
        self.text_align = 0
        self.rop2 = 13                   # R2_COPYPEN; R2_NOP (11) draws nothing

    def copy(self) -> "_State":
        other = _State()
        other.__dict__.update({k: (QPen(v) if isinstance(v, QPen) else v)
                               for k, v in self.__dict__.items()})
        return other


class _Player:
    """Plays records into a painter: what WMF and EMF have in common."""

    def __init__(self):
        self.state = _State()
        self.saved: list = []
        self.objects: dict = {}
        self.path: Optional[QPainterPath] = None
        self.painter: Optional[QPainter] = None

    def _new_object(self, obj) -> None:
        index = 0
        while index in self.objects:
            index += 1
        self.objects[index] = obj

    def _select(self, obj) -> None:
        if obj is None:
            return
        kind, value = obj
        if kind == "pen":
            self.state.pen = value
        elif kind == "brush":
            self.state.brush = value
        elif kind == "font":
            self.state.font, self.state.font_height = value

    def _shape(self, path: QPainterPath, fill: bool = True, stroke: bool = True) -> None:
        if self.path is not None:
            self.path.addPath(path)
            return
        if self.state.rop2 == 11:
            return                       # R2_NOP: drawn without a mark (a frame for the editor)
        p = self.painter
        path.setFillRule(self.state.fill_rule)
        if fill and self.state.brush is not None:
            p.fillPath(path, self.state.brush)
        if stroke and self.state.pen is not None:
            p.strokePath(path, self.state.pen)

    def _polygon(self, points: list, closed: bool) -> None:
        path = QPainterPath()
        if not points:
            return
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
        if closed:
            path.closeSubpath()
            self._shape(path)
        else:
            self._shape(path, fill=False)

    def _text(self, x: float, y: float, text: str, height: float) -> None:
        if not text.strip():
            return
        p = self.painter
        font = QFont(self.state.font)
        font.setPixelSize(max(1, int(round(abs(height or 12)))))
        p.save()
        p.setFont(font)
        p.setPen(self.state.text_colour)
        metrics = p.fontMetrics()
        align = self.state.text_align
        if align & 0x0006 == 0x0006:                         # TA_CENTER
            x -= metrics.horizontalAdvance(text) / 2
        elif align & 0x0002:                                  # TA_RIGHT
            x -= metrics.horizontalAdvance(text)
        if align & 0x0018 == 0x0018:                         # TA_BASELINE
            pass
        elif align & 0x0008:                                  # TA_BOTTOM
            y -= metrics.descent()
        else:                                                 # TA_TOP
            y += metrics.ascent()
        p.drawText(QPointF(x, y), text)
        p.restore()

    def _image(self, image: Optional[QImage], dest: QRectF) -> None:
        if image is not None and dest.width() and dest.height():
            self.painter.drawImage(dest.normalized(), image)


def _surface(width_pt: float, height_pt: float, natural: tuple, scale: float):
    """(image, painter, size in pixels) for a picture drawn at the size asked,
    else its own (*natural*, points)."""
    w = width_pt or natural[0] or 100.0
    h = height_pt or natural[1] or 100.0
    big = max(w, h) * scale
    if big > 2400:                      # a logo needs no more than this
        scale *= 2400 / big
    pw, ph = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    image = QImage(pw, ph, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    return image, painter, (pw, ph)


# -- WMF ----------------------------------------------------------------------------------------
#: records that draw: the window is the one set before the first of them
_WMF_DRAWS = {0x0324, 0x0325, 0x0538, 0x041B, 0x0418, 0x061C, 0x0213, 0x0521, 0x0A32,
              0x0B41, 0x0F43, 0x0940}

class _Wmf(_Player):
    def __init__(self, data: bytes):
        super().__init__()
        self.data = data
        offset = 0
        self.bounds = None
        self.inch = 1440
        if struct.unpack_from("<I", data, 0)[0] == WMF_PLACEABLE:
            left, top, right, bottom, inch = struct.unpack_from("<hhhhH", data, 6)
            self.bounds = QRectF(left, top, right - left, bottom - top).normalized()
            self.inch = inch or 1440
            offset = 22
        _type, words = struct.unpack_from("<HH", data, offset)
        self.start = offset + words * 2

    def _records(self):
        data, at = self.data, self.start
        while at + 6 <= len(data):
            size, function = struct.unpack_from("<IH", data, at)
            if size < 3:
                return
            yield function, data[at + 6: at + size * 2]
            if function == 0:
                return
            at += size * 2

    def draw(self, width_pt: float, height_pt: float, scale: float) -> Optional[QImage]:
        # the window its drawing is written in: the placeable header's, or
        # the first SetWindowExt
        org, ext = QPointF(0, 0), None
        for function, p in self._records():
            if function == 0x020B and len(p) >= 4:
                y, x = struct.unpack_from("<hh", p, 0)
                org = QPointF(x, y)
            elif function == 0x020C and len(p) >= 4:
                ext = struct.unpack_from("<hh", p, 0)[::-1]
            elif function in _WMF_DRAWS:
                break                    # its window is set by the first drawing
        window = QRectF(org.x(), org.y(), ext[0], ext[1]) if ext else None
        frame = self.bounds or window
        if frame is None or not frame.width() or not frame.height():
            return None
        natural = (abs(frame.width()) / self.inch * 72, abs(frame.height()) / self.inch * 72)
        image, painter, (pw, ph) = _surface(width_pt, height_pt, natural, scale)
        self.painter = painter
        view = window if window is not None and window.width() and window.height() else frame
        self.size_px = (pw, ph)
        self.org = QPointF(view.x(), view.y())
        self.ext = (view.width(), view.height())
        self._place()
        try:
            for function, p in self._records():
                self._play(function, p)
        finally:
            painter.end()
        return image

    def _place(self) -> None:
        """Logical units to the picture: the window (org, ext) fills it."""
        pw, ph = self.size_px
        transform = QTransform()
        transform.scale(pw / self.ext[0], ph / self.ext[1])
        transform.translate(-self.org.x(), -self.org.y())
        self.painter.setTransform(transform)

    def _points(self, p: bytes, count: int, at: int = 2) -> list:
        return [struct.unpack_from("<hh", p, at + 4 * i) for i in range(count)]

    def _play(self, f: int, p: bytes) -> None:  # noqa: C901 (one record kind a branch)
        s = self.state
        if f == 0x020B:                                   # SetWindowOrg
            y, x = struct.unpack_from("<hh", p, 0)
            self.org = QPointF(x, y)
            self._place()
        elif f == 0x020C:                                 # SetWindowExt
            h, w = struct.unpack_from("<hh", p, 0)
            if w and h:
                self.ext = (w, h)
                self._place()
        elif f == 0x02FA:                                 # CreatePenIndirect
            style, width, _y, colour = struct.unpack_from("<HhhI", p, 0)
            self._new_object(("pen", _pen(style, width, colour)))
        elif f == 0x02FC:                                 # CreateBrushIndirect
            style, colour, hatch = struct.unpack_from("<HIH", p, 0)
            self._new_object(("brush", _brush(style, colour, hatch)))
        elif f == 0x02FB:                                 # CreateFontIndirect
            height, _w, _esc, _orient, weight = struct.unpack_from("<hhhhh", p, 0)
            italic = p[10] if len(p) > 10 else 0
            face = p[18:50].split(b"\0", 1)[0].decode("latin-1", "replace") or "Arial"
            font = QFont(face)
            font.setBold(weight >= 600)
            font.setItalic(bool(italic))
            self._new_object(("font", (font, height)))
        elif f in (0x00F7, 0x01F9, 0x0142, 0x06FF):      # palette, pattern brushes, region
            self._new_object(("other", None))
        elif f == 0x012D:                                 # SelectObject
            self._select(self.objects.get(struct.unpack_from("<H", p, 0)[0]))
        elif f == 0x01F0:                                 # DeleteObject
            self.objects.pop(struct.unpack_from("<H", p, 0)[0], None)
        elif f == 0x0106:                                 # SetPolyFillMode
            s.fill_rule = Qt.WindingFill if struct.unpack_from("<H", p, 0)[0] == 2 \
                else Qt.OddEvenFill
        elif f == 0x0209:                                 # SetTextColor
            s.text_colour = _colour(struct.unpack_from("<I", p, 0)[0])
        elif f == 0x0104:                                 # SetROP2
            s.rop2 = struct.unpack_from("<H", p, 0)[0]
        elif f == 0x012E:                                 # SetTextAlign
            s.text_align = struct.unpack_from("<H", p, 0)[0]
        elif f == 0x0324:                                 # Polygon
            n = struct.unpack_from("<H", p, 0)[0]
            self._polygon(self._points(p, n), True)
        elif f == 0x0325:                                 # Polyline
            n = struct.unpack_from("<H", p, 0)[0]
            self._polygon(self._points(p, n), False)
        elif f == 0x0538:                                 # PolyPolygon
            polys = struct.unpack_from("<H", p, 0)[0]
            counts = struct.unpack_from(f"<{polys}H", p, 2)
            at = 2 + 2 * polys
            path = QPainterPath()
            for n in counts:
                pts = self._points(p, n, at)
                at += 4 * n
                if pts:
                    path.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
                    path.closeSubpath()
            self._shape(path)
        elif f in (0x041B, 0x0418):                       # Rectangle, Ellipse
            bottom, right, top, left = struct.unpack_from("<hhhh", p, 0)
            path = QPainterPath()
            box = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
            path.addRect(box) if f == 0x041B else path.addEllipse(box)
            self._shape(path)
        elif f == 0x061C:                                 # RoundRect
            h, w, bottom, right, top, left = struct.unpack_from("<hhhhhh", p, 0)
            path = QPainterPath()
            path.addRoundedRect(QRectF(QPointF(left, top), QPointF(right, bottom)).normalized(),
                                abs(w) / 2, abs(h) / 2)
            self._shape(path)
        elif f == 0x0214:                                 # MoveTo
            y, x = struct.unpack_from("<hh", p, 0)
            s.position = QPointF(x, y)
        elif f == 0x0213:                                 # LineTo
            y, x = struct.unpack_from("<hh", p, 0)
            path = QPainterPath(s.position)
            path.lineTo(x, y)
            self._shape(path, fill=False)
            s.position = QPointF(x, y)
        elif f == 0x0521:                                 # TextOut
            n = struct.unpack_from("<H", p, 0)[0]
            text = p[2:2 + n].decode("latin-1", "replace")
            at = 2 + n + (n & 1)
            y, x = struct.unpack_from("<hh", p, at)
            self._text(x, y, text, getattr(s, "font_height", 12))
        elif f == 0x0A32:                                 # ExtTextOut
            y, x, n, options = struct.unpack_from("<hhhH", p, 0)
            at = 8 + (8 if options & 0x0006 else 0)
            text = p[at:at + n].decode("latin-1", "replace")
            self._text(x, y, text, getattr(s, "font_height", 12))
        elif f == 0x001E:                                 # SaveDC
            self.saved.append(s.copy())
        elif f == 0x0127:                                 # RestoreDC
            if self.saved:
                self.state = self.saved.pop()
        elif f in (0x0B41, 0x0F43, 0x0940):              # DIBStretchBlt, StretchDIB, DIBBitBlt
            self._bitmap(f, p)

    def _bitmap(self, f: int, p: bytes) -> None:
        if f == 0x0F43:      # StretchDIB: rop(4) usage(2) srcH srcW srcY srcX destH destW destY destX
            dh, dw, dy, dx = struct.unpack_from("<hhhh", p, 14)
            image = _dib(p[22:])
        elif f == 0x0B41:    # DIBStretchBlt: rop(4) srcH srcW srcY srcX destH destW destY destX
            dh, dw, dy, dx = struct.unpack_from("<hhhh", p, 12)
            image = _dib(p[20:])
        else:                # DIBBitBlt: rop(4) srcY srcX destH destW destY destX
            dh, dw, dy, dx = struct.unpack_from("<hhhh", p, 8)
            image = _dib(p[16:])
        self._image(image, QRectF(dx, dy, dw, dh))


# -- EMF ----------------------------------------------------------------------------------------
_STOCK = {0: ("brush", QBrush(QColor("white"))), 1: ("brush", QBrush(QColor("#c0c0c0"))),
          2: ("brush", QBrush(QColor("#808080"))), 3: ("brush", QBrush(QColor("#404040"))),
          4: ("brush", QBrush(QColor("black"))), 5: ("brush", None),
          6: ("pen", QPen(QColor("white"), 0)), 7: ("pen", QPen(QColor("black"), 0)),
          8: ("pen", None)}


class _Emf(_Player):
    def __init__(self, data: bytes):
        super().__init__()
        self.data = data
        bl, bt, br, bb = struct.unpack_from("<iiii", data, 8)        # bounds, device units
        fl, ft, fr, fb = struct.unpack_from("<iiii", data, 24)       # frame, 0.01 mm
        self.bounds = QRectF(QPointF(bl, bt), QPointF(br, bb)).normalized()
        self.frame_mm = ((fr - fl) / 100.0, (fb - ft) / 100.0)
        dev_w, dev_h = struct.unpack_from("<ii", data, 72)           # reference device, pixels
        mm_w, mm_h = struct.unpack_from("<ii", data, 80)             # and millimetres
        self.px_per_mm = (dev_w / mm_w if mm_w else 3.78, dev_h / mm_h if mm_h else 3.78)

    def _records(self):
        data, at = self.data, 0
        while at + 8 <= len(data):
            kind, size = struct.unpack_from("<II", data, at)
            if size < 8:
                return
            yield kind, data[at + 8: at + size]
            if kind == 14:                                # EMR_EOF
                return
            at += size

    def draw(self, width_pt: float, height_pt: float, scale: float) -> Optional[QImage]:
        natural = (self.frame_mm[0] / 25.4 * 72, self.frame_mm[1] / 25.4 * 72)
        image, painter, (pw, ph) = _surface(width_pt, height_pt, natural, scale)
        self.painter = painter
        # the frame in device pixels of the reference device: the drawing's
        # logical units map to it through the window and viewport
        self.page = QTransform()
        frame_px = QRectF(0, 0, self.frame_mm[0] * self.px_per_mm[0],
                          self.frame_mm[1] * self.px_per_mm[1])
        bounds = self.bounds if self.bounds.width() and self.bounds.height() else frame_px
        self.page.scale(pw / bounds.width(), ph / bounds.height())
        self.page.translate(-bounds.x(), -bounds.y())
        self.window = [0.0, 0.0, 1.0, 1.0]       # org x, y, ext x, y
        self.viewport = [0.0, 0.0, 1.0, 1.0]
        self.window_set = self.viewport_set = False
        self.world = QTransform()
        self._place()
        try:
            for kind, p in self._records():
                self._play(kind, p)
        finally:
            painter.end()
        return image

    def _place(self) -> None:
        """The painter's transform from logical units: world, then window to
        viewport (MM_ANISOTROPIC as Office writes them), then the page."""
        t = QTransform(self.world)
        if self.window_set and self.viewport_set and self.window[2] and self.window[3]:
            m = QTransform()
            m.translate(self.viewport[0], self.viewport[1])
            m.scale(self.viewport[2] / self.window[2], self.viewport[3] / self.window[3])
            m.translate(-self.window[0], -self.window[1])
            t = t * m
        elif self.window_set and self.window[2] and self.window[3]:
            m = QTransform()
            m.translate(-self.window[0], -self.window[1])
            t = t * m
        self.painter.setTransform(t * self.page)

    def _points(self, p: bytes, count: int, at: int, small: bool) -> list:
        fmt, step = ("<hh", 4) if small else ("<ii", 8)
        return [struct.unpack_from(fmt, p, at + step * i) for i in range(count)]

    def _play(self, k: int, p: bytes) -> None:  # noqa: C901 (one record kind a branch)
        s = self.state
        if k in (3, 4, 86, 87):                           # Polygon(16), Polyline(16)
            small = k > 80
            n = struct.unpack_from("<I", p, 16)[0]
            self._polygon(self._points(p, n, 20, small), k in (3, 86))
        elif k in (8, 91, 7, 90):                         # PolyPolygon(16), PolyPolyline(16)
            small = k > 80
            polys, _total = struct.unpack_from("<II", p, 16)
            counts = struct.unpack_from(f"<{polys}I", p, 24)
            at = 24 + 4 * polys
            path = QPainterPath()
            for n in counts:
                pts = self._points(p, n, at, small)
                at += n * (4 if small else 8)
                if pts:
                    path.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
                    if k in (8, 91):
                        path.closeSubpath()
            self._shape(path, fill=k in (8, 91))
        elif k in (2, 85, 5, 88):                         # PolyBezier(To)(16)
            small = k > 80
            n = struct.unpack_from("<I", p, 16)[0]
            pts = self._points(p, n, 20, small)
            to = k in (5, 88)
            path = QPainterPath(s.position if to else QPointF(*pts[0]))
            rest = pts if to else pts[1:]
            for i in range(0, len(rest) - 2, 3):
                path.cubicTo(QPointF(*rest[i]), QPointF(*rest[i + 1]), QPointF(*rest[i + 2]))
            if rest:
                s.position = QPointF(*rest[-1])
            self._shape(path, fill=False)
        elif k in (6, 89):                                # PolylineTo(16)
            small = k > 80
            n = struct.unpack_from("<I", p, 16)[0]
            path = QPainterPath(s.position)
            for x, y in self._points(p, n, 20, small):
                path.lineTo(x, y)
                s.position = QPointF(x, y)
            self._shape(path, fill=False)
        elif k == 9:                                      # SetWindowExtEx
            self.window[2], self.window[3] = struct.unpack_from("<ii", p, 0)
            self.window_set = True
            self._place()
        elif k == 10:                                     # SetWindowOrgEx
            self.window[0], self.window[1] = struct.unpack_from("<ii", p, 0)
            self.window_set = True
            self._place()
        elif k == 11:                                     # SetViewportExtEx
            self.viewport[2], self.viewport[3] = struct.unpack_from("<ii", p, 0)
            self.viewport_set = True
            self._place()
        elif k == 12:                                     # SetViewportOrgEx
            self.viewport[0], self.viewport[1] = struct.unpack_from("<ii", p, 0)
            self.viewport_set = True
            self._place()
        elif k == 19:                                     # SetPolyFillMode
            s.fill_rule = Qt.WindingFill if struct.unpack_from("<I", p, 0)[0] == 2 \
                else Qt.OddEvenFill
        elif k == 24:                                     # SetTextColor
            s.text_colour = _colour(struct.unpack_from("<I", p, 0)[0])
        elif k == 20:                                     # SetROP2
            s.rop2 = struct.unpack_from("<I", p, 0)[0]
        elif k == 22:                                     # SetTextAlign
            s.text_align = struct.unpack_from("<I", p, 0)[0]
        elif k == 27:                                     # MoveToEx
            s.position = QPointF(*struct.unpack_from("<ii", p, 0))
            if self.path is not None:
                self.path.moveTo(s.position)
        elif k == 54:                                     # LineTo
            x, y = struct.unpack_from("<ii", p, 0)
            if self.path is not None:
                self.path.lineTo(x, y)
            else:
                path = QPainterPath(s.position)
                path.lineTo(x, y)
                self._shape(path, fill=False)
            s.position = QPointF(x, y)
        elif k == 33:                                     # SaveDC
            self.saved.append((s.copy(), QTransform(self.world), list(self.window),
                               list(self.viewport), self.window_set, self.viewport_set))
        elif k == 34:                                     # RestoreDC
            if self.saved:
                (self.state, self.world, self.window, self.viewport,
                 self.window_set, self.viewport_set) = self.saved.pop()
                self._place()
        elif k == 35:                                     # SetWorldTransform
            m11, m12, m21, m22, dx, dy = struct.unpack_from("<6f", p, 0)
            self.world = QTransform(m11, m12, m21, m22, dx, dy)
            self._place()
        elif k == 36:                                     # ModifyWorldTransform
            m11, m12, m21, m22, dx, dy = struct.unpack_from("<6f", p, 0)
            mode = struct.unpack_from("<I", p, 24)[0]
            given = QTransform(m11, m12, m21, m22, dx, dy)
            if mode == 1:
                self.world = QTransform()
            elif mode == 2:
                self.world = given * self.world
            elif mode == 3:
                self.world = self.world * given
            elif mode == 4:
                self.world = given
            self._place()
        elif k == 37:                                     # SelectObject
            index = struct.unpack_from("<I", p, 0)[0]
            self._select(_STOCK.get(index & 0x7FFFFFFF) if index & 0x80000000
                         else self.objects.get(index))
        elif k == 38:                                     # CreatePen
            index, style, width, _y, colour = struct.unpack_from("<IIiiI", p, 0)
            self.objects[index] = ("pen", _pen(style, width, colour))
        elif k == 95:                                     # ExtCreatePen
            index = struct.unpack_from("<I", p, 0)[0]
            style, width, _bs, colour = struct.unpack_from("<IIII", p, 20)
            self.objects[index] = ("pen", _pen(style, width, colour))
        elif k == 39:                                     # CreateBrushIndirect
            index, style, colour, hatch = struct.unpack_from("<IIII", p, 0)
            self.objects[index] = ("brush", _brush(style, colour, hatch))
        elif k == 82:                                     # ExtCreateFontIndirectW
            index, height, _w, _esc, _orient, weight = struct.unpack_from("<Iiiiii", p, 0)
            italic = p[24] if len(p) > 24 else 0
            face = p[32:96].decode("utf-16-le", "replace").split("\0", 1)[0] or "Arial"
            font = QFont(face)
            font.setBold(weight >= 600)
            font.setItalic(bool(italic))
            self.objects[index] = ("font", (font, height))
        elif k == 40:                                     # DeleteObject
            self.objects.pop(struct.unpack_from("<I", p, 0)[0], None)
        elif k in (42, 43):                               # Ellipse, Rectangle
            left, top, right, bottom = struct.unpack_from("<iiii", p, 0)
            box = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
            path = QPainterPath()
            path.addEllipse(box) if k == 42 else path.addRect(box)
            self._shape(path)
        elif k == 44:                                     # RoundRect
            left, top, right, bottom, w, h = struct.unpack_from("<iiiiii", p, 0)
            path = QPainterPath()
            path.addRoundedRect(QRectF(QPointF(left, top), QPointF(right, bottom)).normalized(),
                                abs(w) / 2, abs(h) / 2)
            self._shape(path)
        elif k == 59:                                     # BeginPath
            self.path = QPainterPath()
        elif k == 60:                                     # EndPath
            pass
        elif k == 61:                                     # CloseFigure
            if self.path is not None:
                self.path.closeSubpath()
        elif k in (62, 63, 64):                           # FillPath, StrokeAndFillPath, StrokePath
            path, self.path = self.path, None
            if path is not None:
                self._shape(path, fill=k in (62, 63), stroke=k in (63, 64))
        elif k == 84:                                     # ExtTextOutW
            x, y = struct.unpack_from("<ii", p, 36)
            n, off = struct.unpack_from("<II", p, 44)
            text = self.data_slice(p, off - 8, n * 2).decode("utf-16-le", "replace")
            self._text(x, y, text, getattr(s, "font_height", 12))
        elif k == 81:                                     # StretchDIBits
            left, top, _r, _b = struct.unpack_from("<iiii", p, 0)
            dx, dy = struct.unpack_from("<ii", p, 16)
            off_bmi, cb_bmi, off_bits, cb_bits = struct.unpack_from("<IIII", p, 32)
            dw, dh = struct.unpack_from("<ii", p, 64)
            dib = p[off_bmi - 8: off_bmi - 8 + cb_bmi] + p[off_bits - 8: off_bits - 8 + cb_bits]
            self._image(_dib(dib), QRectF(dx, dy, dw, dh))

    @staticmethod
    def data_slice(p: bytes, at: int, n: int) -> bytes:
        return p[at:at + n] if at >= 0 else b""
