"""Common infrastructure for every object that can live on a page."""
from __future__ import annotations

import math
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
                           QPolygonF, QTransform)
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

# The dashes each named line type is drawn with, in multiples of the line
# width — which is how PDF writes them, so a line type read out of a Bluebeam
# file and one chosen from the list are the same thing.
DASH_ARRAYS = {
    "solid": [],
    "dash": [4.0, 2.0],
    "dot": [1.0, 2.0],
    "dashdot": [4.0, 2.0, 1.0, 2.0],
    "dashdotdot": [4.0, 2.0, 1.0, 2.0, 1.0, 2.0],
    "long dash": [8.0, 3.0],
    "centre": [10.0, 2.5, 2.0, 2.5],
    "phantom": [10.0, 2.5, 2.0, 2.5, 2.0, 2.5],
    "hidden": [3.0, 2.0],
}

# Hatch patterns, by the names Bluebeam uses for them. A hatched fill is how
# a section is shown as concrete or as steel, and a tool set full of sections
# is worth nothing if they all come in as flat colour.
HATCH_PATTERNS = {
    "": Qt.SolidPattern,
    "solid": Qt.SolidPattern,
    "horizontal": Qt.HorPattern,
    "vertical": Qt.VerPattern,
    "cross": Qt.CrossPattern,
    "up": Qt.BDiagPattern,
    "down": Qt.FDiagPattern,
    "diagonal cross": Qt.DiagCrossPattern,
    "dots": Qt.Dense5Pattern,
    "dense": Qt.Dense3Pattern,
}


def hatch_named(name: str):
    """Bluebeam's name for a hatch, as a brush pattern.

    Its files spell these a dozen ways — "Hatch-DiagonalUp", "diagonal up",
    "/FDiag" — so the name is read for what it says rather than matched
    letter for letter.
    """
    # "DiagonalUp" is two words; so is "Hatch-Diagonal_Up". Split on a capital
    # as well as on anything that is not a letter, or half the names it is
    # given would come through as one word nobody recognises.
    spaced = []
    for index, character in enumerate(name or ""):
        if not character.isalpha():
            spaced.append(" ")
            continue
        if index and character.isupper() and (name[index - 1].islower()
                                              or name[index - 1].isdigit()):
            spaced.append(" ")
        spaced.append(character)
    words = set("".join(spaced).lower().split())
    if not words or "solid" in words:
        return Qt.SolidPattern
    diagonal = bool(words & {"diagonal", "diag", "bdiag", "fdiag"})
    if "cross" in words:
        return Qt.DiagCrossPattern if diagonal else Qt.CrossPattern
    if words & {"up", "bdiag", "forward"}:
        return Qt.BDiagPattern
    if words & {"down", "fdiag", "backward"}:
        return Qt.FDiagPattern
    if diagonal:
        return Qt.FDiagPattern
    if words & {"horizontal", "hor"}:
        return Qt.HorPattern
    if words & {"vertical", "ver"}:
        return Qt.VerPattern
    if words & {"dot", "dots", "dotted", "concrete", "gravel", "sand"}:
        return Qt.Dense5Pattern
    if words & {"dense", "steel", "solidfill"}:
        return Qt.Dense3Pattern
    return Qt.SolidPattern

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
    # A hatch pattern over the fill, by name — "" is a plain fill.
    hatch: str = ""
    # A dash pattern of this line's own, in multiples of its width. Empty
    # means the named line style decides, which is the usual case; a line
    # read out of a Bluebeam file brings its own.
    dash_array: tuple = ()

    def dashes(self) -> list:
        """The dashes this line is drawn with, in multiples of its width."""
        if self.dash_array:
            return [float(step) for step in self.dash_array if float(step) > 0]
        return list(DASH_ARRAYS.get(self.line_style, []))

    def pen(self, scale: float = 1.0) -> QPen:
        colour = QColor(self.stroke or "#000000")
        colour.setAlphaF(max(0.0, min(1.0, self.opacity)))
        pen = QPen(colour)
        pen.setWidthF(max(self.width * scale, 0.01))
        dashes = self.dashes()
        if dashes:
            # A dash pattern of its own beats the named style, and a round cap
            # would fill the gaps back in on a dotted line.
            pen.setStyle(Qt.CustomDashLine)
            pen.setDashPattern(dashes)
            pen.setCapStyle(Qt.FlatCap)
        else:
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
        return QBrush(colour, hatch_named(self.hatch))

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
    # The eight corners and edges resize, and the pointer says which way.
    "nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
    "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
    "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
    "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
    "rot": Qt.CrossCursor,
    # A call-out's arrow heads and hinges are numbered — l0, e0, l1, e1 —
    # because there is no limit to how many a comment may need, so they are
    # matched by their shape below rather than listed here.
    # A measurement's own words: dragged to move them, turned to angle them.
    "lbl": Qt.SizeAllCursor,
    "lblrot": Qt.CrossCursor,
}


def cursor_for_handle(key: str):
    """The pointer for a handle, including the numbered ones.

    A polyline has as many handles as it has corners — v0, v1, v2 — so they
    cannot be listed one by one. Every one of them moves a point, which is
    what the pointing hand means everywhere else in the app.
    """
    if key in HANDLE_CURSORS:
        return HANDLE_CURSORS[key]
    letter, rest = key[:1], key[1:]
    if rest.isdigit():
        if letter == "e":
            # A hinge slides along a line and hops from side to side: an open
            # hand says "take hold of this", which is what it is for.
            return Qt.OpenHandCursor
        if letter in ("v", "l", "c", "n", "r"):
            return Qt.PointingHandCursor
    return Qt.SizeAllCursor


# ---------------------------------------------------------------------------
# Base item
# ---------------------------------------------------------------------------

#: What a reviewer can say about a markup, and the order it reads in.
#:
#: These are the PDF's own review states, not names invented here: an
#: annotation's status travels as a reply annotation carrying ``/State`` and
#: ``/StateModel /Review``, which is how Acrobat and Bluebeam both record it.
#: So a drawing marked up here comes back to the consultant with its statuses
#: intact, and one they have been through arrives here with theirs.
STATUSES = ["None", "Accepted", "Rejected", "Cancelled", "Completed"]

#: What each status is drawn in, in the markups list. A colour is how a
#: reviewer reads a page of them without reading any of them.
STATUS_COLOURS = {
    "Accepted": "#2f9e44",
    "Rejected": "#e03131",
    "Cancelled": "#868e96",
    "Completed": "#1971c2",
}


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
        # Where a markup has got to in a review: one of :data:`STATUSES`, empty
        # for one nobody has ruled on yet. Who said so and when are kept with
        # it, because "rejected" without a name on it is not an answer anybody
        # can go back to.
        self.status = ""
        self.status_by = ""
        self.status_at = ""
        # The conversation about this markup, oldest first: each reply is
        # ``{"author": …, "text": …, "at": …}``. A review is a back and forth,
        # and a single comment field can only hold one end of it.
        self.replies: list[dict] = []
        self.created = datetime.now().isoformat(timespec="seconds")
        self.modified = self.created
        self.locked = False
        self.printable = True
        # Hidden: still in the document, just not shown — the layers panel and
        # "Show hidden" bring it back. Flattened: made part of the drawing, no
        # longer a markup that can be picked out or edited.
        self.hidden = False
        self.flattened = False
        # Recoverable flattening keeps this complete source item in the
        # file. Irreversible flattening replaces source items with one visual
        # recording whose flag is False, so Recover never promises data that
        # was deliberately discarded.
        self.flatten_recoverable = True
        self.locked_before_flatten = False
        # Markups sharing a group id are selected, moved and copied together.
        self.group = ""
        # Holes taken out of this shape, each a ring of local points. A hole
        # belongs to the shape it came out of rather than being a markup of
        # its own, so moving the shape takes its holes with it. Any closed
        # shape can own them — a slab with two lift shafts in it is the same
        # idea whether it was drawn as an area measurement, a polygon or a
        # rectangle.
        self.cutouts: list[list[QPointF]] = []
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

    def set_status(self, status: str, who: str = "") -> None:
        """Say where this markup has got to, and sign it.

        "None" is a state a reviewer can deliberately go back to — it means
        "no longer decided" rather than "never looked at" — so it is recorded
        with its name and time like any other.
        """
        self.status = "" if status in ("", "None") else str(status)
        self.status_by = who
        self.status_at = datetime.now().isoformat(timespec="seconds") if who else ""
        self.touch()

    def add_reply(self, text: str, who: str = "") -> dict:
        """Add to the conversation about this markup."""
        reply = {"author": who, "text": str(text),
                 "at": datetime.now().isoformat(timespec="seconds")}
        self.replies.append(reply)
        self.touch()
        return reply

    def latest_word(self) -> str:
        """The last thing said about this markup, whoever said it."""
        if self.replies:
            return str(self.replies[-1].get("text", ""))
        return self.summary()

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
        box = self.local_rect().normalized().adjusted(-margin, -margin, margin, margin)
        if self.ROTATABLE:
            # The rotation handle stands off above the box. Left out of here it
            # is painted outside the item's own rectangle, so Qt clips it and
            # leaves a smear of it behind every time the markup moves.
            box.setTop(box.top() - ROTATE_OFFSET - HANDLE_SIZE)
        return box

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.local_rect().normalized().adjusted(-3, -3, 3, 3))
        return path

    def center(self) -> QPointF:
        return self.mapToScene(self.local_rect().center())

    def set_item_rotation(self, angle: float, zero_snap: float = 2.0) -> None:
        """Turn around the visible centre, normalising an almost-zero angle.

        Qt's raw ``setRotation`` turns around (0, 0) unless a caller happened
        to set an origin first.  A markup should instead stay centred however
        its rotation was changed (handle, Properties, or an edit transition).
        """
        angle = float(angle) % 360.0
        if angle > 180.0:
            angle -= 360.0
        if abs(angle) <= zero_snap:
            angle = 0.0
        centre = self.local_rect().center()
        before = self.mapToScene(centre)
        self.setTransformOriginPoint(centre)
        self.setRotation(angle)
        after = self.mapToScene(centre)
        parent = self.parentItem()
        if parent is not None:
            correction = parent.mapFromScene(before) - parent.mapFromScene(after)
        else:
            correction = before - after
        self.setPos(self.pos() + correction)
        self.touch()
        self.geometryChanged.emit()

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

    def control_dots(self) -> set[str]:
        """Handles drawn as a dot rather than as a square.

        A dimension's value carries one: it is a control point sitting on the
        text, not a corner of a box, and it should not look like one.
        """
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
            angle = round(angle / (15 if keep_ratio else 1)) * (15 if keep_ratio else 1)
            self.set_item_rotation(angle)
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
        if self.group:
            # A grouped markup is part of one thing, and the view draws one box
            # round the lot; its own outline and handles would only be noise.
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
        dots = self.control_dots()
        for key, point in points.items():
            if key == "rot":
                painter.setBrush(QBrush(QColor(120, 200, 120)))
                painter.drawEllipse(point, half, half)
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                painter.drawLine(point, QPointF(rect.center().x(), rect.top()))
            elif key in dots:
                painter.setBrush(QBrush(QColor(20, 90, 200)))
                painter.drawEllipse(point, half * 0.8, half * 0.8)
                painter.setBrush(QBrush(QColor(255, 255, 255)))
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
    # -- holes -------------------------------------------------------------
    def outline_ring(self) -> list:
        """This shape as a closed ring of local points, or empty if it is not.

        What a hole can be put inside. A shape that does not enclose anything
        returns nothing and is never offered as somewhere to put one.
        """
        return []

    def holes_path(self) -> QPainterPath:
        """Every hole as one path, for subtracting from a fill."""
        path = QPainterPath()
        for hole in self.cutouts:
            if len(hole) >= 3:
                path.addPolygon(QPolygonF(hole))
                path.closeSubpath()
        return path

    def paint_cutouts(self, painter: QPainter) -> None:
        """The holes, outlined so it is obvious what has been taken out."""
        if not self.cutouts:
            return
        pen = QPen(QColor(self.style.stroke or "#1971c2"))
        pen.setWidthF(max(self.style.width, 0.6))
        pen.setStyle(Qt.DashLine)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for hole in self.cutouts:
            if len(hole) >= 3:
                painter.drawPolygon(QPolygonF(hole))
        painter.restore()

    def cutouts_as_data(self) -> list:
        return [[[round(p.x(), 3), round(p.y(), 3)] for p in hole]
                for hole in self.cutouts]

    def cutouts_from_data(self, data: dict) -> None:
        self.cutouts = [[QPointF(x, y) for x, y in hole]
                        for hole in data.get("cutouts", [])]

    def base_dict(self) -> dict:
        return {
            "type": self.TYPE,
            "uid": self.uid,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "z": self.zValue(),
            "rotation": self.rotation(),
            "transform": [self.transform().m11(), self.transform().m12(),
                          self.transform().m21(), self.transform().m22(),
                          self.transform().dx(), self.transform().dy()],
            "style": self.style.to_dict(),
            "author": self.author,
            "subject": self.subject,
            "comment": self.comment,
            "label": self.label,
            "layer": self.layer,
            "status": self.status,
            "status_by": self.status_by,
            "status_at": self.status_at,
            "replies": [dict(reply) for reply in self.replies],
            "created": self.created,
            "modified": self.modified,
            "locked": self.locked,
            "printable": self.printable,
            "hidden": self.hidden,
            "flattened": self.flattened,
            "flatten_recoverable": self.flatten_recoverable,
            "locked_before_flatten": self.locked_before_flatten,
            "group": self.group,
        }

    def serialize(self) -> dict:
        return self.base_dict()

    def load_base(self, data: dict) -> None:
        self.uid = data.get("uid", self.uid)
        self.setPos(QPointF(float(data.get("x", 0)), float(data.get("y", 0))))
        self.setZValue(float(data.get("z", 0)))
        matrix = data.get("transform")
        if isinstance(matrix, (list, tuple)) and len(matrix) == 6:
            self.setTransform(QTransform(float(matrix[0]), float(matrix[1]),
                                         float(matrix[2]), float(matrix[3]),
                                         float(matrix[4]), float(matrix[5])))
        self.style = Style.from_dict(data.get("style", {}))
        self.group = str(data.get("group", ""))
        self.author = data.get("author", "")
        self.subject = data.get("subject", "")
        self.comment = data.get("comment", "")
        self.label = data.get("label", "")
        self.layer = data.get("layer", "Markups")
        self.status = data.get("status", "")
        self.status_by = data.get("status_by", "")
        self.status_at = data.get("status_at", "")
        self.replies = [dict(reply) for reply in (data.get("replies") or [])
                        if isinstance(reply, dict)]
        self.created = data.get("created", self.created)
        self.modified = data.get("modified", self.modified)
        self.printable = bool(data.get("printable", True))
        self.hidden = bool(data.get("hidden", False))
        self.flattened = bool(data.get("flattened", False))
        self.flatten_recoverable = bool(data.get("flatten_recoverable", True))
        self.locked_before_flatten = bool(data.get("locked_before_flatten", False))
        self.set_locked(bool(data.get("locked", False)) or self.flattened)
        if self.flattened:
            self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        if self.hidden:
            self.setVisible(False)
        # Rotation is always about the visible object's centre.  Keeping the
        # origin implicit at (0, 0) made a reopened rotated object orbit away
        # from the position stored in the document.
        self.setTransformOriginPoint(self.local_rect().center())
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
