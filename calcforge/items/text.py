"""Text-bearing markups: text boxes, callouts, sticky notes and stamps."""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QAbstractTextDocumentLayout, QBrush, QColor, QPainter,
                           QPainterPath, QPalette, QPen, QTextCursor,
                           QTextDocument, QTextOption)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsTextItem,
                               QStyle, QStyleOptionGraphicsItem)

from .base import HANDLE_SIZE, MarkupItem, Style, arrow_path, register_item

STAMP_PRESETS = {
    "APPROVED": "#2f9e44",
    "REVIEWED": "#1971c2",
    "FOR CONSTRUCTION": "#0ca678",
    "FOR REVIEW": "#f59f00",
    "AS BUILT": "#7048e8",
    "PRELIMINARY": "#e8590c",
    "NOT FOR CONSTRUCTION": "#e03131",
    "SUPERSEDED": "#868e96",
    "REJECTED": "#c2255c",
    "DRAFT": "#495057",
    "CONFIDENTIAL": "#c92a2a",
    "ISSUED FOR TENDER": "#1098ad",
}


class _InlineEditor(QGraphicsTextItem):
    """A text editor with none of Qt's own decoration.

    Qt draws a dotted frame around a focused text item, sized to the text
    rather than to the region. On a text box that already has its own outline
    that reads as a second, wrongly-sized box floating in the corner.
    """

    def paint(self, painter: QPainter, option, widget=None) -> None:
        trimmed = QStyleOptionGraphicsItem(option)
        trimmed.state &= ~QStyle.State_HasFocus
        trimmed.state &= ~QStyle.State_Selected
        super().paint(painter, trimmed, widget)


class _TextBase(MarkupItem):
    """Shared rich-text behaviour: document, layout, in-place editing."""

    HAS_TEXT = True

    def __init__(self, text: str = "", rect: Optional[QRectF] = None):
        super().__init__()
        self._rect = QRectF(rect) if rect else QRectF(0, 0, 180, 60)
        self.style = Style(stroke="#1971c2", fill="#ffffff", fill_opacity=1.0,
                           width=1.0, text_color="#111318", font_size=10.0)
        self.auto_size = True
        # Parented to the item so Qt owns it: a document that outlives its
        # item, or dies before it, fires contentsChanged into a half-destroyed
        # receiver on the way out.
        self.doc = QTextDocument(self)
        self.doc.setDocumentMargin(0)
        self.doc.setPlainText(text)
        self._editor: Optional[QGraphicsTextItem] = None
        self._editing = False
        self.doc.contentsChanged.connect(self._on_contents_changed)

    # -- content -----------------------------------------------------------
    def text(self) -> str:
        return self.doc.toPlainText()

    def set_text(self, text: str) -> None:
        self.doc.setPlainText(text)
        self.apply_style()

    def html(self) -> str:
        return self.doc.toHtml()

    def set_html(self, html: str) -> None:
        self.doc.setHtml(html)

    def _on_contents_changed(self) -> None:
        self.prepareGeometryChange()
        if self.auto_size:
            self._fit_height()
        self.touch()
        self.update()
        self.contentChanged.emit()

    def apply_style(self) -> None:
        self.doc.setDefaultFont(self.style.font())
        option = QTextOption()
        option.setAlignment(self.style.alignment() & Qt.AlignHorizontal_Mask)
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.doc.setDefaultTextOption(option)
        self.doc.setTextWidth(max(self.text_rect().width(), 8.0))
        if self._editor is not None:
            self._editor.setDefaultTextColor(self.style.text_qcolor())
        self.prepareGeometryChange()
        if self.auto_size:
            self._fit_height()
        self.update()

    def text_rect(self) -> QRectF:
        pad = self.style.padding
        return self._rect.normalized().adjusted(pad, pad, -pad, -pad)

    def _fit_height(self) -> None:
        self.doc.setTextWidth(max(self.text_rect().width(), 8.0))
        needed = self.doc.size().height() + 2 * self.style.padding
        if needed > self._rect.height():
            self._rect.setHeight(needed)

    # -- geometry ----------------------------------------------------------
    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)
        self.apply_style()
        self._sync_editor()

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._rect.normalized().adjusted(-3, -3, 3, 3))
        return path

    # -- editing -----------------------------------------------------------
    def begin_edit(self) -> None:
        if self.locked:
            return
        if self._editor is None:
            self._editor = _InlineEditor(self)
            self._editor.setDocument(self.doc)
            self._editor.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self._editor.setDefaultTextColor(self.style.text_qcolor())
        self._editor.setTextInteractionFlags(Qt.TextEditorInteraction)
        self._sync_editor()
        self._editor.show()
        self._editing = True
        self._editor.setFocus(Qt.MouseFocusReason)
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._editor.setTextCursor(cursor)
        self.update()

    def end_edit(self) -> None:
        if self._editor is not None:
            self._editor.setTextInteractionFlags(Qt.NoTextInteraction)
            self._editor.clearFocus()
            # The editor is thrown away rather than hidden. A hidden one keeps
            # a live view on the same document for the rest of the item's life,
            # and two owners of one document is a lifetime problem waiting for
            # the moment the page is torn down.
            self._editor.setDocument(None)
            self._editor.setParentItem(None)
            scene = self._editor.scene()
            if scene is not None:
                scene.removeItem(self._editor)
            self._editor = None
        self._editing = False
        self.apply_style()
        self.update()

    @property
    def editing(self) -> bool:
        return self._editing

    def _sync_editor(self) -> None:
        if self._editor is None:
            return
        rect = self.text_rect()
        self._editor.setPos(rect.topLeft())
        self._editor.setTextWidth(max(rect.width(), 8.0))

    # -- painting ----------------------------------------------------------
    def paint_text(self, painter: QPainter) -> None:
        if self._editing:
            return
        rect = self.text_rect()
        painter.save()
        painter.translate(rect.topLeft())
        painter.setClipRect(QRectF(0, 0, rect.width() + 1, rect.height() + 1))
        self.doc.setTextWidth(max(rect.width(), 8.0))
        offset = 0.0
        if self.style.valign in ("middle", "bottom"):
            spare = rect.height() - self.doc.size().height()
            offset = max(spare, 0) * (0.5 if self.style.valign == "middle" else 1.0)
            painter.translate(0, offset)
        # The colour has to be handed to the document layout explicitly. Left
        # to itself it takes the application's palette, which would mean the
        # words on the paper changed colour when the user switched the
        # interface to dark — the sheet is the sheet, whatever the frame does.
        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette.setColor(QPalette.Text, self.style.text_qcolor())
        context.clip = QRectF(0, 0, rect.width() + 1, rect.height() + 1)
        painter.setPen(QPen(self.style.text_qcolor()))
        self.doc.documentLayout().draw(painter, context)
        painter.restore()

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({
            "rect": [self._rect.x(), self._rect.y(), self._rect.width(), self._rect.height()],
            "html": self.doc.toHtml(),
            "auto_size": self.auto_size,
        })
        return data

    def deserialize(self, data: dict) -> None:
        values = data.get("rect", [0, 0, 160, 50])
        self._rect = QRectF(*values)
        self.auto_size = bool(data.get("auto_size", True))
        self.load_base(data)
        html = data.get("html")
        if html:
            self.doc.setHtml(html)
        else:
            self.doc.setPlainText(data.get("text", ""))
        self.apply_style()


@register_item
class TextItem(_TextBase):
    """A free text box with optional border and fill."""

    TYPE = "text"
    NAME = "Text box"

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._rect.normalized()
        painter.setBrush(self.style.brush())
        painter.setPen(self.style.pen() if self.style.stroke and self.style.width > 0
                       else QPen(Qt.NoPen))
        if self.style.corner_radius > 0:
            painter.drawRoundedRect(rect, self.style.corner_radius, self.style.corner_radius)
        else:
            painter.drawRect(rect)
        self.paint_text(painter)

    def summary(self) -> str:
        return self.comment or self.text().strip().replace("\n", " ")[:120]


@register_item
class CalloutItem(_TextBase):
    """A text box with a leader line pointing at something."""

    TYPE = "callout"
    NAME = "Callout"

    def __init__(self, text: str = "", rect: Optional[QRectF] = None,
                 leader: Optional[list[QPointF]] = None):
        super().__init__(text, rect)
        self.style.arrow_end = "arrow"
        self.leader: list[QPointF] = [QPointF(p) for p in (leader or [])]
        if not self.leader:
            box = self._rect
            self.leader = [QPointF(box.left() - 60, box.bottom() + 50),
                           QPointF(box.left() - 20, box.bottom() + 10)]

    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def boundingRect(self) -> QRectF:
        rect = QRectF(self._rect)
        for point in self.leader:
            rect = rect.united(QRectF(point.x() - 1, point.y() - 1, 2, 2))
        margin = self.style.width + HANDLE_SIZE + 12
        return rect.normalized().adjusted(-margin, -margin, margin, margin)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._rect.normalized().adjusted(-3, -3, 3, 3))
        if len(self.leader) >= 2:
            from PySide6.QtGui import QPainterPathStroker
            line = QPainterPath(self.leader[0])
            for point in self.leader[1:]:
                line.lineTo(point)
            line.lineTo(self._anchor_point())
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.style.width, 6.0) + 4)
            path.addPath(stroker.createStroke(line))
        return path

    def _anchor_point(self) -> QPointF:
        """Where the leader meets the box: nearest point on the box edge."""
        rect = self._rect.normalized()
        if not self.leader:
            return rect.center()
        source = self.leader[-1]
        x = min(max(source.x(), rect.left()), rect.right())
        y = min(max(source.y(), rect.top()), rect.bottom())
        if rect.contains(source):
            return rect.center()
        # push onto the nearest edge
        distances = {
            "left": abs(source.x() - rect.left()), "right": abs(source.x() - rect.right()),
            "top": abs(source.y() - rect.top()), "bottom": abs(source.y() - rect.bottom()),
        }
        side = min(distances, key=distances.get)
        if side == "left":
            return QPointF(rect.left(), y)
        if side == "right":
            return QPointF(rect.right(), y)
        if side == "top":
            return QPointF(x, rect.top())
        return QPointF(x, rect.bottom())

    def handle_points(self) -> dict[str, QPointF]:
        handles = super().handle_points()
        handles.pop("rot", None)
        for index, point in enumerate(self.leader):
            handles[f"l{index}"] = QPointF(point)
        return handles

    def leader_handles(self) -> set[str]:
        """The handles that belong to the arrow rather than to the box."""
        return {f"l{index}" for index in range(len(self.leader))}

    def move_keeping_leader(self, position: QPointF) -> None:
        """Move the box and leave the arrow pointing where it was pointing.

        The leader is held in the item's own coordinates, so without this the
        arrow travels with the box and stops pointing at the thing it was
        drawn to point at.
        """
        delta = position - self.pos()
        if not delta.isNull() and self.leader:
            self.prepareGeometryChange()
            self.leader = [QPointF(point.x() - delta.x(), point.y() - delta.y())
                           for point in self.leader]
        self.setPos(position)

    def move_handle(self, key: str, local_pos: QPointF, keep_ratio: bool = False) -> None:
        if key.startswith("l"):
            index = int(key[1:])
            if 0 <= index < len(self.leader):
                self.prepareGeometryChange()
                self.leader[index] = QPointF(local_pos)
                self.geometryChanged.emit()
            return
        # Resizing the box must not drag the arrow along with it: the arrow
        # points at something on the page, and stays pointing at it until it
        # is moved on purpose. Its points are held in the item's own
        # coordinates, so they are pinned in scene terms across the resize.
        pinned = [self.mapToScene(point) for point in self.leader]
        super().move_handle(key, local_pos, keep_ratio)
        if pinned:
            self.prepareGeometryChange()
            self.leader = [self.mapFromScene(point) for point in pinned]

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = self.style.pen()
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        if self.leader:
            path = QPainterPath(self.leader[0])
            for point in self.leader[1:]:
                path.lineTo(point)
            path.lineTo(self._anchor_point())
            painter.drawPath(path)
            if self.style.arrow_end != "none" and len(self.leader) >= 2:
                tip = self.leader[0]
                following = self.leader[1]
                angle = math.atan2(tip.y() - following.y(), tip.x() - following.x())
                colour = QColor(self.style.stroke)
                colour.setAlphaF(self.style.opacity)
                painter.setBrush(QBrush(colour))
                painter.drawPath(arrow_path(tip, angle, max(self.style.width * 4.5, 8.0),
                                            self.style.arrow_end))
        rect = self._rect.normalized()
        painter.setBrush(self.style.brush())
        painter.setPen(pen)
        painter.drawRoundedRect(rect, self.style.corner_radius, self.style.corner_radius)
        self.paint_text(painter)

    def serialize(self) -> dict:
        data = super().serialize()
        data["leader"] = [[p.x(), p.y()] for p in self.leader]
        return data

    def deserialize(self, data: dict) -> None:
        super().deserialize(data)
        self.leader = [QPointF(x, y) for x, y in data.get("leader", [])]

    def summary(self) -> str:
        return self.comment or self.text().strip().replace("\n", " ")[:120]


@register_item
class NoteItem(MarkupItem):
    """A collapsed sticky note; its text lives in the markups list."""

    TYPE = "note"
    NAME = "Note"
    RESIZABLE = False
    ROTATABLE = False
    SIZE = 20.0

    def __init__(self, comment: str = ""):
        super().__init__()
        self.comment = comment
        self.style = Style(stroke="#b8860b", fill="#ffe066", fill_opacity=1.0, width=0.8)

    def local_rect(self) -> QRectF:
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.local_rect()
        painter.setBrush(self.style.brush())
        painter.setPen(self.style.pen())
        painter.drawRoundedRect(rect, 3, 3)
        pen = QPen(QColor(120, 90, 10))
        pen.setWidthF(0.9)
        painter.setPen(pen)
        for index in range(3):
            y = rect.top() + 6 + index * 4.5
            painter.drawLine(QPointF(rect.left() + 4, y), QPointF(rect.right() - 4, y))

    def summary(self) -> str:
        return self.comment.replace("\n", " ")[:160]

    def serialize(self) -> dict:
        return self.base_dict()


@register_item
class StampItem(MarkupItem):
    """A rotatable text stamp with an optional signature line."""

    TYPE = "stamp"
    NAME = "Stamp"

    def __init__(self, text: str = "APPROVED", rect: Optional[QRectF] = None):
        super().__init__()
        self.text = text
        self.subtext = ""
        self._rect = QRectF(rect) if rect else QRectF(0, 0, 190, 58)
        colour = STAMP_PRESETS.get(text.upper(), "#e03131")
        self.style = Style(stroke=colour, fill=colour, fill_opacity=0.06, width=2.0,
                           text_color=colour, font_size=17.0, bold=True,
                           corner_radius=5.0, align="center", valign="middle")

    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._rect.normalized()
        painter.setBrush(self.style.brush())
        painter.setPen(self.style.pen())
        painter.drawRoundedRect(rect, self.style.corner_radius, self.style.corner_radius)
        # Shrink the title until it fits the box.
        from PySide6.QtGui import QFontMetricsF
        from ..core.typography import set_size
        available = rect.width() - 14
        font = self.style.font()
        size = float(font.pixelSize())
        while size > 5:
            font = set_size(font, size)
            if QFontMetricsF(font).horizontalAdvance(self.text) <= available:
                break
            size -= 1.0
        painter.setFont(font)
        painter.setPen(QPen(self.style.text_qcolor()))
        body = rect.adjusted(6, 4, -6, -4)
        if self.subtext:
            title_rect = QRectF(body.x(), body.y(), body.width(), body.height() * 0.62)
            painter.drawText(title_rect, Qt.AlignCenter, self.text)
            small = set_size(font, max(font.pixelSize() * 0.45, 5.0))
            small.setBold(False)
            painter.setFont(small)
            sub_rect = QRectF(body.x(), body.y() + body.height() * 0.60,
                              body.width(), body.height() * 0.40)
            painter.drawText(sub_rect, Qt.AlignCenter, self.subtext)
        else:
            painter.drawText(body, Qt.AlignCenter, self.text)

    def summary(self) -> str:
        return self.comment or self.text

    def display_name(self) -> str:
        return self.label or f"Stamp · {self.text}"

    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({"text": self.text, "subtext": self.subtext,
                     "rect": [self._rect.x(), self._rect.y(),
                              self._rect.width(), self._rect.height()]})
        return data

    def deserialize(self, data: dict) -> None:
        self.text = data.get("text", "APPROVED")
        self.subtext = data.get("subtext", "")
        self._rect = QRectF(*data.get("rect", [0, 0, 190, 58]))
        self.load_base(data)
