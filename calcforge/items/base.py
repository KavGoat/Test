"""Common infrastructure for every object that can live on a page."""
from __future__ import annotations

import math
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
                           QPolygonF)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsObject,
                               QStyleOptionGraphicsItem, QWidget)

from ..core.typography import page_font

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

LINE_STYLES = {
    "solid": Qt.SolidLine,
    "dash": Qt.DashLine,
    "dot": Qt.DotLine,
    "dashdot": Qt.DashDotLine,
    "dashdotdot": Qt.DashDotDotLine,
}

ARROW_HEADS = ["none", "arrow", "open", "dot", "square", "diamond", "slash", "half"]

# Bluebeam-ish default palette offered in colour pickers.
PALETTE = [
    "#e03131", "#f76707", "#f59f00", "#2f9e44", "#0ca678", "#1971c2",
    "#4263eb", "#7048e8", "#c2255c", "#000000", "#495057", "#adb5bd",
    "#ffffff", "#ffe066", "#8ce99a", "#a5d8ff", "#ffc9c9", "#d0bfff",
]


@dataclass
class Style:
    """Appearance shared by all markups."""

    stroke: str = "#e03131"
    fill: str = ""                     # empty means no fill
    width: float = 1.5
    line_style: str = "solid"
    opacity: float = 1.0
    fill_opacity: float = 0.35
    font_family: str = "Segoe UI"
    font_size: float = 10.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    text_color: str = "#111318"
    align: str = "left"
    valign: str = "top"
    arrow_start: str = "none"
    arrow_end: str = "none"
    blend: str = "normal"              # 'multiply' for highlighter
    corner_radius: float = 0.0
    padding: float = 4.0

    def pen(self, scale: float = 1.0) -> QPen:
        colour = QColor(self.stroke or "#000000")
        colour.setAlphaF(max(0.0, min(1.0, self.opacity)))
        pen = QPen(colour)
        pen.setWidthF(max(self.width * scale, 0.01))
        pen.setStyle(LINE_STYLES.get(self.line_style, Qt.SolidLine))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCosmetic(False)
        return pen

    def brush(self) -> QBrush:
        if not self.fill:
            return QBrush(Qt.NoBrush)
        colour = QColor(self.fill)
        colour.setAlphaF(max(0.0, min(1.0, self.fill_opacity * self.opacity)))
        return QBrush(colour)

    def font(self) -> QFont:
        return page_font(self.font_family, self.font_size, self.bold, self.italic,
                         self.underline)

    def text_qcolor(self) -> QColor:
        colour = QColor(self.text_color or "#000000")
        colour.setAlphaF(max(0.0, min(1.0, self.opacity)))
        return colour

    def alignment(self) -> Qt.AlignmentFlag:
        horizontal = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter,
                      "right": Qt.AlignRight, "justify": Qt.AlignJustify}
        vertical = {"top": Qt.AlignTop, "middle": Qt.AlignVCenter, "bottom": Qt.AlignBottom}
        return horizontal.get(self.align, Qt.AlignLeft) | vertical.get(self.valign, Qt.AlignTop)

    def copy(self) -> "Style":
        return Style(**asdict(self))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Style":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


# ---------------------------------------------------------------------------
# Item registry
# ---------------------------------------------------------------------------

ITEM_REGISTRY: dict[str, type] = {}


def register_item(cls):
    """Class decorator that makes an item type loadable from a saved file."""
    ITEM_REGISTRY[cls.TYPE] = cls
    return cls


def build_item(data: dict):
    """Recreate an item from its serialised form."""
    cls = ITEM_REGISTRY.get(data.get("type"))
    if cls is None:
        return None
    item = cls()
    item.deserialize(data)
    return item


# ---------------------------------------------------------------------------
# Handles
# ---------------------------------------------------------------------------

HANDLE_SIZE = 7.0
ROTATE_OFFSET = 22.0

CORNER_HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")

HANDLE_CURSORS = {
    "nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
    "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
    "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
    "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
    "rot": Qt.CrossCursor,
    # A callout's arrow: pointing at things, not resizing.
    "l0": Qt.PointingHandCursor, "l1": Qt.PointingHandCursor,
    "l2": Qt.PointingHandCursor, "l3": Qt.PointingHandCursor,
}


# ---------------------------------------------------------------------------
# Base item
# ---------------------------------------------------------------------------

class MarkupItem(QGraphicsObject):
    """Base class: selection handles, style, metadata and serialisation."""

    TYPE = "markup"
    NAME = "Markup"
    RESIZABLE = True
    ROTATABLE = True
    HAS_TEXT = False

    geometryChanged = Signal()
    contentChanged = Signal()

    def __init__(self):
        super().__init__()
        self.uid = uuid.uuid4().hex
        self.style = Style()
        self.author = ""
        self.subject = ""
        self.comment = ""
        self.label = ""
        self.layer = "Markups"
        self.status = ""
        self.created = datetime.now().isoformat(timespec="seconds")
        self.modified = self.created
        self.locked = False
        self.printable = True
        self._handles_visible = True
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setTransformOriginPoint(QPointF(0, 0))

    # -- metadata ----------------------------------------------------------
    def touch(self) -> None:
        self.modified = datetime.now().isoformat(timespec="seconds")

    def display_name(self) -> str:
        return self.label or self.NAME

    def summary(self) -> str:
        """Text shown in the markups list."""
        return self.comment or self.label or ""

    def set_locked(self, locked: bool) -> None:
        self.locked = bool(locked)
        self.setFlag(QGraphicsItem.ItemIsMovable, not self.locked)
        self.update()

    # -- geometry ----------------------------------------------------------
    def local_rect(self) -> QRectF:
        """Geometry rectangle in item coordinates (excluding pen width)."""
        return QRectF(0, 0, 0, 0)

    def set_local_rect(self, rect: QRectF) -> None:
        return

    def boundingRect(self) -> QRectF:
        margin = self.style.width + HANDLE_SIZE + 4
        return self.local_rect().normalized().adjusted(-margin, -margin, margin, margin)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.local_rect().normalized().adjusted(-3, -3, 3, 3))
        return path

    def center(self) -> QPointF:
        return self.mapToScene(self.local_rect().center())

    # -- handles -----------------------------------------------------------
    def handle_points(self) -> dict[str, QPointF]:
        if not self.RESIZABLE:
            return {}
        rect = self.local_rect().normalized()
        points = {
            "nw": rect.topLeft(), "n": QPointF(rect.center().x(), rect.top()),
            "ne": rect.topRight(), "e": QPointF(rect.right(), rect.center().y()),
            "se": rect.bottomRight(), "s": QPointF(rect.center().x(), rect.bottom()),
            "sw": rect.bottomLeft(), "w": QPointF(rect.left(), rect.center().y()),
        }
        if self.ROTATABLE:
            points["rot"] = QPointF(rect.center().x(), rect.top() - ROTATE_OFFSET)
        return points

    def leader_handles(self) -> set[str]:
        """Handles that move something other than the item's own box."""
        return set()

    def handle_at(self, local_pos: QPointF, tolerance: float = HANDLE_SIZE) -> Optional[str]:
        if self.locked:
            return None
        for key, point in self.handle_points().items():
            if (abs(point.x() - local_pos.x()) <= tolerance
                    and abs(point.y() - local_pos.y()) <= tolerance):
                return key
        return None

    def move_handle(self, key: str, local_pos: QPointF, keep_ratio: bool = False) -> None:
        rect = self.local_rect().normalized()
        if key == "rot":
            centre = rect.center()
            angle = math.degrees(math.atan2(local_pos.y() - centre.y(),
                                            local_pos.x() - centre.x())) + 90
            self.setTransformOriginPoint(centre)
            self.setRotation(round(angle / (15 if keep_ratio else 1)) * (15 if keep_ratio else 1))
            return
        left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
        if "w" in key:
            left = local_pos.x()
        if "e" in key:
            right = local_pos.x()
        if "n" in key:
            top = local_pos.y()
        if "s" in key:
            bottom = local_pos.y()
        new_rect = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
        if keep_ratio and rect.width() > 0 and rect.height() > 0 and len(key) == 2:
            ratio = rect.height() / rect.width()
            new_rect.setHeight(max(new_rect.width() * ratio, 1.0))
        if new_rect.width() < 2:
            new_rect.setWidth(2)
        if new_rect.height() < 2:
            new_rect.setHeight(2)
        self.prepareGeometryChange()
        self.set_local_rect(new_rect)
        self.touch()
        self.geometryChanged.emit()

    def paint_handles(self, painter: QPainter) -> None:
        if not self.isSelected() or not self._handles_visible:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.local_rect().normalized()
        outline = QPen(QColor(30, 110, 220, 200))
        outline.setWidthF(0.8)
        outline.setStyle(Qt.DashLine)
        painter.setPen(outline)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
        if self.locked:
            painter.restore()
            return
        painter.setPen(QPen(QColor(20, 90, 200), 0.9))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        half = HANDLE_SIZE / 2
        points = self.handle_points()
        # A markup can own handles that are not corners of its box — a
        # callout's arrow, for one. They are drawn as orange diamonds so it is
        # obvious which handle moves what.
        leader = self.leader_handles()
        for key, point in points.items():
            if key == "rot":
                painter.setBrush(QBrush(QColor(120, 200, 120)))
                painter.drawEllipse(point, half, half)
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                painter.drawLine(point, QPointF(rect.center().x(), rect.top()))
            elif key in leader:
                painter.setPen(QPen(QColor(200, 90, 20), 0.9))
                painter.setBrush(QBrush(QColor(255, 170, 80)))
                painter.drawPolygon(QPolygonF([
                    QPointF(point.x(), point.y() - half - 1),
                    QPointF(point.x() + half + 1, point.y()),
                    QPointF(point.x(), point.y() + half + 1),
                    QPointF(point.x() - half - 1, point.y())]))
                painter.setPen(QPen(QColor(20, 90, 200), 0.9))
                painter.setBrush(QBrush(QColor(255, 255, 255)))
            else:
                painter.drawRect(QRectF(point.x() - half, point.y() - half,
                                        HANDLE_SIZE, HANDLE_SIZE))
        painter.restore()

    # -- painting helpers --------------------------------------------------
    def apply_blend(self, painter: QPainter) -> None:
        if self.style.blend == "multiply":
            painter.setCompositionMode(QPainter.CompositionMode_Multiply)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None) -> None:
        painter.save()
        self.apply_blend(painter)
        self.paint_content(painter)
        painter.restore()
        self.paint_handles(painter)

    def paint_content(self, painter: QPainter) -> None:
        return

    # -- serialisation -----------------------------------------------------
    def base_dict(self) -> dict:
        return {
            "type": self.TYPE,
            "uid": self.uid,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "z": self.zValue(),
            "rotation": self.rotation(),
            "style": self.style.to_dict(),
            "author": self.author,
            "subject": self.subject,
            "comment": self.comment,
            "label": self.label,
            "layer": self.layer,
            "status": self.status,
            "created": self.created,
            "modified": self.modified,
            "locked": self.locked,
            "printable": self.printable,
        }

    def serialize(self) -> dict:
        return self.base_dict()

    def load_base(self, data: dict) -> None:
        self.uid = data.get("uid", self.uid)
        self.setPos(QPointF(float(data.get("x", 0)), float(data.get("y", 0))))
        self.setZValue(float(data.get("z", 0)))
        self.style = Style.from_dict(data.get("style", {}))
        self.author = data.get("author", "")
        self.subject = data.get("subject", "")
        self.comment = data.get("comment", "")
        self.label = data.get("label", "")
        self.layer = data.get("layer", "Markups")
        self.status = data.get("status", "")
        self.created = data.get("created", self.created)
        self.modified = data.get("modified", self.modified)
        self.printable = bool(data.get("printable", True))
        self.set_locked(bool(data.get("locked", False)))
        self.setRotation(float(data.get("rotation", 0)))

    def deserialize(self, data: dict) -> None:
        self.load_base(data)

    def clone(self):
        data = self.serialize()
        data["uid"] = uuid.uuid4().hex
        item = build_item(data)
        if item is not None:
            item.setPos(self.pos() + QPointF(12, 12))
        return item

    # -- convenience -------------------------------------------------------
    def assets_used(self) -> set[str]:
        return set()

    def refresh(self, workspace=None, page=None) -> None:
        """Recalculate anything derived (results, measurements)."""
        return


# ---------------------------------------------------------------------------
# Drawing helpers shared by several item types
# ---------------------------------------------------------------------------

def arrow_path(tip: QPointF, direction: float, size: float, kind: str) -> QPainterPath:
    """Build an arrowhead of *kind* at *tip*, pointing along *direction* (radians)."""
    path = QPainterPath()
    if kind in ("none", ""):
        return path
    if kind in ("arrow", "open", "half"):
        spread = math.radians(24)
        left = tip - QPointF(math.cos(direction - spread) * size,
                             math.sin(direction - spread) * size)
        right = tip - QPointF(math.cos(direction + spread) * size,
                              math.sin(direction + spread) * size)
        if kind == "arrow":
            polygon = QPolygonF([tip, left, right])
            path.addPolygon(polygon)
            path.closeSubpath()
        elif kind == "half":
            path.moveTo(left)
            path.lineTo(tip)
        else:
            path.moveTo(left)
            path.lineTo(tip)
            path.lineTo(right)
    elif kind == "dot":
        path.addEllipse(tip, size * 0.4, size * 0.4)
    elif kind == "square":
        path.addRect(QRectF(tip.x() - size * 0.35, tip.y() - size * 0.35,
                            size * 0.7, size * 0.7))
    elif kind == "diamond":
        polygon = QPolygonF([
            tip + QPointF(math.cos(direction) * size * 0.5, math.sin(direction) * size * 0.5),
            tip + QPointF(math.cos(direction + math.pi / 2) * size * 0.35,
                          math.sin(direction + math.pi / 2) * size * 0.35),
            tip - QPointF(math.cos(direction) * size * 0.5, math.sin(direction) * size * 0.5),
            tip + QPointF(math.cos(direction - math.pi / 2) * size * 0.35,
                          math.sin(direction - math.pi / 2) * size * 0.35),
        ])
        path.addPolygon(polygon)
        path.closeSubpath()
    elif kind == "slash":
        offset = QPointF(math.cos(direction + math.pi / 4) * size * 0.6,
                         math.sin(direction + math.pi / 4) * size * 0.6)
        path.moveTo(tip - offset)
        path.lineTo(tip + offset)
    return path


def cloud_path(polygon: QPolygonF, radius: float, closed: bool = True) -> QPainterPath:
    """Convert a polyline into a Bluebeam-style revision cloud."""
    path = QPainterPath()
    points = list(polygon)
    if len(points) < 2:
        return path
    if closed and points[0] != points[-1]:
        points.append(points[0])
    radius = max(radius, 1.5)
    started = False
    for start, end in zip(points, points[1:]):
        delta = end - start
        length = math.hypot(delta.x(), delta.y())
        if length < 1e-6:
            continue
        bumps = max(int(round(length / (radius * 1.9))), 1)
        step = length / bumps
        angle = math.atan2(delta.y(), delta.x())
        for index in range(bumps):
            bump_start = start + QPointF(math.cos(angle), math.sin(angle)) * (index * step)
            bump_end = start + QPointF(math.cos(angle), math.sin(angle)) * ((index + 1) * step)
            mid = (bump_start + bump_end) / 2
            box = QRectF(mid.x() - step / 2, mid.y() - step / 2, step, step)
            sweep_start = math.degrees(math.atan2(-(bump_start.y() - mid.y()),
                                                  bump_start.x() - mid.x()))
            if not started:
                path.arcMoveTo(box, sweep_start)
                started = True
            path.arcTo(box, sweep_start, -200)
    return path


def dash_pattern_preview(style: str) -> list[float]:
    return {"solid": [], "dash": [4, 3], "dot": [1, 3],
            "dashdot": [5, 3, 1, 3], "dashdotdot": [5, 3, 1, 3, 1, 3]}.get(style, [])
