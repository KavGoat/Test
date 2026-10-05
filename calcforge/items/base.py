"""Common infrastructure for every object that can live on a page."""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from copy import deepcopy
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

# The dashes each named line type is drawn with, in points — as PDF writes
# them. A line's thickness does not change them: a heavy dashed line has the
# same dashes as a light one, the way Bluebeam draws it. Style.dash_scale
# stretches or tightens them.
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
    "short dash": [2.0, 2.0],
    "dense dot": [1.0, 1.0],
    "sparse dot": [1.0, 5.0],
    "long dash dot": [12.0, 3.0, 1.0, 3.0],
    "long dash dot dot": [12.0, 3.0, 1.0, 3.0, 1.0, 3.0],
    "border": [8.0, 2.0, 8.0, 2.0, 1.0, 2.0],
    "divide": [8.0, 2.0, 1.0, 2.0, 1.0, 2.0],
    "double dash": [6.0, 2.0, 6.0, 6.0],
    "dash long gap": [4.0, 6.0],
}

# Hatch patterns, by the names Bluebeam uses for them. A hatched fill is how
# a section is shown as concrete or as steel, and a tool set full of sections
# is worth nothing if they all come in as flat colour.
class _HatchNames(dict):
    """Every hatch the pickers offer, in order ("" is none).

    Values are unused; kept a mapping so older callers iterating it still work.
    """


def _hatch_names():
    from . import hatches
    return _HatchNames({"": None, **{name: None for name in hatches.NAMES}})


HATCH_PATTERNS = _hatch_names()


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

#: The distance between hatch lines at a hatch scale of one, in page points.
HATCH_CELL = 8.0


def paint_hatch(painter: QPainter, region: QPainterPath, style) -> None:
    """Draw *style*'s hatch over *region* as real lines, clipped to it."""
    if region is None or region.isEmpty() or not style.hatched():
        return
    from . import hatches
    ink = QColor(style.hatch_color or style.stroke or "#000000")
    ink.setAlphaF(max(0.0, min(1.0, style.opacity
                                * getattr(style, "hatch_opacity", 1.0))))
    if style.hatch_tile:
        hatches.paint_tile(painter, region, style.hatch_tile, style.hatch_scale, ink)
        return
    hatches.paint(painter, region, style.hatch, style.hatch_scale, ink)


def _is_hatch(name: str) -> bool:
    from . import hatches
    return hatches.is_hatch(name)


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
    arrow_size: float = 1.0
    blend: str = "normal"              # 'multiply' for highlighter
    corner_radius: float = 0.0
    padding: float = 4.0
    # A hatch pattern, by name — "" is none. It is drawn over the fill in a
    # colour of its own: the fill is a solid wash, the hatch is linework.
    hatch: str = ""
    hatch_scale: float = 1.0
    hatch_color: str = "#000000"
    # How solid the hatch lines are, on their own: fill_opacity is the
    # fill's, opacity the whole markup's (line, fill and hatch together).
    hatch_opacity: float = 1.0
    # A dash pattern of this line's own, in multiples of its width. Empty
    # means the named line style decides, which is the usual case; a line
    # read out of a Bluebeam file brings its own.
    dash_array: tuple = ()
    # How far apart the dashes and dots of the line type are: 1 is as the
    # type defines them, 2 twice as long and twice as far apart.
    dash_scale: float = 1.0
    # A hatch drawn from a tile of its own rather than from the library: a
    # Bluebeam pattern, brought across as the linework its cell holds.
    # {"step_x", "step_y", "x", "y", "strokes"}; empty for a library hatch.
    hatch_tile: dict = field(default_factory=dict)
    # The outline of words in a box: "rect", or "circle" for Bluebeam's
    # circled text.
    text_shape: str = "rect"
    # Where the words sit inside the box — left, top, right, bottom — when
    # that is not the same all round: circled text sets its words in the
    # square inside the circle. Empty means the padding, all round.
    text_margins: tuple = ()

    def dashes(self) -> list:
        """The dashes this line is drawn with, in points, spacing applied."""
        scale = max(float(self.dash_scale or 1.0), 0.01)
        if self.dash_array:
            steps = [float(step) for step in self.dash_array if float(step) > 0]
        else:
            steps = list(DASH_ARRAYS.get(self.line_style, []))
        return [step * scale for step in steps]

    def pen(self, scale: float = 1.0) -> QPen:
        key = (self.stroke, self.opacity, self.width, scale, self.line_style,
               self.dash_scale, tuple(self.dash_array or ()))
        made = _PENS.get(key)
        if made is None:
            made = self._make_pen(scale)
            if len(_PENS) > 512:
                _PENS.clear()
            _PENS[key] = made
        return QPen(made)

    def _make_pen(self, scale: float) -> QPen:
        colour = QColor(self.stroke or "#000000")
        colour.setAlphaF(max(0.0, min(1.0, self.opacity)))
        pen = QPen(colour)
        pen.setWidthF(max(self.width * scale, 0.01))
        # Qt counts dashes in line widths; ours are points, so they are
        # divided through — which is what keeps thickness out of the spacing.
        dashes = [step / max(self.width, 0.01) for step in self.dashes()]
        if dashes:
            # A dash pattern of its own beats the named style, and a round cap
            # would fill the gaps back in on a dotted line.
            pen.setStyle(Qt.CustomDashLine)
            pen.setDashPattern(dashes)
            pen.setCapStyle(Qt.FlatCap)
        else:
            pen.setStyle(LINE_STYLES.get(self.line_style, Qt.SolidLine))
            pen.setCapStyle(Qt.FlatCap)
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setCosmetic(False)
        return pen

    def paints_inside(self) -> bool:
        """Whether anything is drawn inside the outline: a fill or a hatch."""
        return bool(self.fill) or self.hatched()

    def hatched(self) -> bool:
        """Whether a hatch pattern is drawn, rather than only a fill."""
        from . import hatches
        return bool(self.hatch_tile) or hatches.is_hatch(self.hatch)

    def brush(self) -> QBrush:
        """The solid fill. A hatch is linework, drawn over it by paint_hatch."""
        if not self.fill:
            return QBrush(Qt.NoBrush)
        colour = QColor(self.fill)
        colour.setAlphaF(max(0.0, min(1.0, self.fill_opacity * self.opacity)))
        return QBrush(colour)

    def hatch_spacing(self) -> float:
        """Distance between hatch lines, in page points. No upper limit."""
        return HATCH_CELL * max(float(self.hatch_scale or 1.0), 1e-12)

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
        return Style(**self.to_dict())

    def to_dict(self) -> dict:
        # Styles are flat scalar records, apart from a possible dash list.
        # Undo and saving visit every style: avoid dataclasses' recursive
        # traversal for immutable values, but still detach mutable dash data.
        return {name: value if isinstance(value, (str, int, float, bool, type(None)))
                else deepcopy(value)
                for name in self.__dataclass_fields__
                for value in (getattr(self, name),)}

    @classmethod
    def from_dict(cls, data: dict) -> "Style":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        if "hatch_color" not in data and known.get("hatch") and \
                _is_hatch(known["hatch"]):
            # Saved before hatch and fill were separate: the hatch was drawn
            # in the fill colour with nothing under it. Keep that look.
            known["hatch_color"] = known.get("fill") or known.get("stroke") or "#000000"
            known["fill"] = ""
        return cls(**known)


# ---------------------------------------------------------------------------
# Item registry
# ---------------------------------------------------------------------------

ITEM_REGISTRY: dict[str, type] = {}


def scale_where(item, page, local: QPointF):
    """The scale that applies to *item* on *page*, read at *local*.

    A page's viewports each carry a scale of their own; a markup measured
    inside one is read at that scale, anything else at the page's.
    """
    if not getattr(page, "viewports", None):
        return page.scale
    where = local
    try:
        frame = getattr(page, "frame", None)
        if (frame is not None and item.scene() is not None
                and frame.scene() is item.scene()):
            where = frame.mapFromScene(item.mapToScene(local))
        else:
            where = item.mapToParent(local)
    except RuntimeError:
        pass
    return page.scale_at(where.x(), where.y())


def register_item(cls):
    """Class decorator that makes an item type loadable from a saved file."""
    ITEM_REGISTRY[cls.TYPE] = cls
    return cls


def rename_groups(data: dict, renamed: dict) -> None:
    """Give a copied markup fresh group names, keeping its arrangement.

    A duplicate that kept the names would join the very group it was copied
    from and move about with it. Every group it is inside gets a new name, and
    the same new name each time that group is met again, so a group inside a
    group is still inside it afterwards.
    """
    path = [str(step) for step in (data.get("group_path") or []) if str(step)]
    if not path and data.get("group"):
        path = [str(data["group"])]
    if not path:
        return
    path = [renamed.setdefault(step, uuid.uuid4().hex[:12]) for step in path]
    data["group_path"] = path
    data["group"] = path[0]


def build_item(data: dict):
    """Recreate an item from its serialised form."""
    cls = ITEM_REGISTRY.get(data.get("type"))
    if cls is None:
        return None
    item = cls()
    item._still_arriving = True
    try:
        item.deserialize(data)
    finally:
        item._still_arriving = False
    return item


# ---------------------------------------------------------------------------
# Handles
# ---------------------------------------------------------------------------

HANDLE_SIZE = 4.0
HANDLE_SCREEN_PX = 4.0
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
        if letter == "w":
            return Qt.SizeHorCursor
        if letter == "z":
            return Qt.SizeVerCursor
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

#: What changes how a markup looks on its page, before it happens.
_CHANGES_THAT_SHOW = (QGraphicsItem.ItemPositionChange, QGraphicsItem.ItemTransformChange,
                      QGraphicsItem.ItemRotationChange, QGraphicsItem.ItemScaleChange,
                      QGraphicsItem.ItemTransformOriginPointChange,
                      QGraphicsItem.ItemZValueChange,
                      QGraphicsItem.ItemVisibleChange, QGraphicsItem.ItemEnabledChange,
                      QGraphicsItem.ItemChildAddedChange, QGraphicsItem.ItemChildRemovedChange)


class MarkupItem(QGraphicsObject):
    """Base class: selection handles, style, metadata and serialisation."""

    TYPE = "markup"
    NAME = "Markup"
    RESIZABLE = True
    ROTATABLE = True
    HAS_TEXT = False

    geometryChanged = Signal()
    contentChanged = Signal()

    #: While this markup is drawn from its page's squares (ui/markuplayer.py),
    #: its size as it was when it went in: it is not changing, and Qt asks
    #: for it twice per markup per frame.
    _baked_rect = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        own = cls.__dict__.get("boundingRect")
        if own is not None and not getattr(own, "_answers_baked", False):
            def boundingRect(self, _own=own):
                baked = self._baked_rect
                return baked if baked is not None else _own(self)
            boundingRect._answers_baked = True
            boundingRect.__doc__ = own.__doc__
            cls.boundingRect = boundingRect

    # -- the page's squares (ui/markuplayer.py) ------------------------------
    def _layer(self):
        return getattr(self.parentItem(), "layer", None)

    def _changing(self) -> None:
        layer = self._layer()
        if layer is not None:
            layer.touched(self)

    def update(self, *args):                 # (no annotation: a Qt slot)
        self._changing()
        super().update(*args)

    def prepareGeometryChange(self):
        self._changing()
        super().prepareGeometryChange()

    def __init__(self):
        super().__init__()
        self.uid = uuid.uuid4().hex
        self.style = Style()
        self.author = ""
        self.subject = ""
        self.comment = ""
        self.label = ""
        # Whether this is the page's own line work rather than somebody's
        # markup: read out of the PDF the page came in on, so that a
        # measurement can snap to the end of a beam. It belongs to the page —
        # it is written as part of it rather than as an annotation, it is not
        # what a snapshot copies, and it is not offered as a guide to line new
        # markups up with, because a drawing is already full of lines.
        self.from_drawing = False
        self.created = datetime.now().isoformat(timespec="seconds")
        self.modified = self.created
        self.locked = False
        self.printable = True
        # Hidden: still in the document, just not shown — Markup ▸ Show hidden
        # brings it back. Flattened: made part of the drawing, no
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
        # And the groups that one is inside, outermost first, when it is
        # inside more than one. A tool set brings these across: a section mark
        # is a bubble and its label grouped together, inside the group that
        # adds the cut line. Clicking takes hold of the outermost — group is
        # always the first step of this — and ungrouping peels one off, so
        # what is inside stays together.
        self.group_path: tuple = ()
        # What the outermost group is called — "Section" for a section mark
        # from a Bluebeam tool set — so it goes back out under that name.
        self.group_title = ""
        # Holes taken out of this shape, each a ring of local points. A hole
        # belongs to the shape it came out of rather than being a markup of
        # its own, so moving the shape takes its holes with it. Any closed
        # shape can own them — a slab with two lift shafts in it is the same
        # idea whether it was drawn as an area measurement, a polygon or a
        # rectangle.
        self.cutouts: list[list[QPointF]] = []
        # Which annotation of the file this markup was read out of, if it was
        # read out of one, and whether it is still exactly as it arrived.
        # See "somebody else's markup" below.
        self.from_annotation = 0
        self.still_theirs = False
        # The annotation's own box on the page (/Rect: x, y, w, h), which is
        # where its file draws it — a dimension's words can sit well outside
        # what the markup measures as its own box.
        self.their_box: tuple = ()
        self._their_look = None
        # One stroke of an annotation that came apart into several markups
        # (a multi-stroke ink line): while all of them are untouched the page
        # draws the annotation, on screen, and they draw nothing there.
        self.split_from = 0
        self.split_theirs = False
        # For the few markups there is nothing to draw from — a stamp is a
        # picture and a company logo, described nowhere but in its own
        # appearance — the file's drawing of it, kept.
        self._their_picture = None
        self.their_picture_asset = ""
        self.their_picture_box: tuple = ()
        # A Bluebeam picture (/IT /SquareImage): the picture fills the box,
        # whatever size it is given, and the box's own border goes over it.
        self.picture_framed = False
        self._stamp_picture_b64 = ""
        # A stamp's drawing kept as SVG linework, drawn as vectors.
        self.stamp_svg = ""
        self._stamp_renderer = None
        # True while the item is being built from a payload. Laying text out
        # and fitting a box are changes as far as touch() is concerned, and
        # they all happen during loading — so a markup would stop being its
        # own file's before it had ever been drawn.
        self._still_arriving = False
        self._handles_visible = True
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setTransformOriginPoint(QPointF(0, 0))

    # -- metadata ----------------------------------------------------------
    def touch(self) -> None:
        """Say this markup has been changed.

        Which is also the moment somebody else's markup becomes one of ours:
        up to here the file it came from was drawing it, and from here this
        application draws it. Moving one does not come through here, so a
        markup dragged across the page is still drawn by its own file.
        """
        self.modified = datetime.now().isoformat(timespec="seconds")
        if not self._still_arriving:
            self.make_it_ours()

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
        if self._baked_rect is not None:
            return self._baked_rect
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
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        import math
        shape = painter.transform()
        zoom = max(math.hypot(shape.m11(), shape.m12()), 0.01)
        handle = HANDLE_SCREEN_PX / zoom
        half = handle / 2
        rect = self.local_rect().normalized()
        outline = QPen(QColor(30, 110, 220, 200))
        outline.setWidthF(0.6 / zoom)
        outline.setStyle(Qt.DashLine)
        painter.setPen(outline)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
        if self.locked:
            painter.restore()
            return
        painter.setPen(QPen(QColor(20, 90, 200), 0.6 / zoom))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        points = self.handle_points()
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
                painter.setPen(QPen(QColor(200, 90, 20), 0.6 / zoom))
                painter.setBrush(QBrush(QColor(255, 170, 80)))
                painter.drawPolygon(QPolygonF([
                    QPointF(point.x(), point.y() - half - 1.0 / zoom),
                    QPointF(point.x() + half + 1.0 / zoom, point.y()),
                    QPointF(point.x(), point.y() + half + 1.0 / zoom),
                    QPointF(point.x() - half - 1.0 / zoom, point.y())]))
                painter.setPen(QPen(QColor(20, 90, 200), 0.6 / zoom))
                painter.setBrush(QBrush(QColor(255, 255, 255)))
            else:
                painter.drawRect(QRectF(point.x() - half, point.y() - half,
                                        handle, handle))
        painter.restore()

    # -- painting helpers --------------------------------------------------
    def apply_blend(self, painter: QPainter) -> None:
        if self.style.blend == "multiply":
            engine = painter.paintEngine()
            if engine is not None and engine.type() == engine.Type.OpenGL2:
                # Qt's OpenGL engine cannot multiply (it paints black): a
                # translucent highlighter over the words instead.
                painter.setOpacity(painter.opacity() * 0.45)
                return
            painter.setCompositionMode(QPainter.CompositionMode_Multiply)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None) -> None:
        painter.save()
        self.apply_blend(painter)
        frame = self.parentItem()
        if not (self.split_theirs and not getattr(frame, "print_mode", True)):
            self.paint_visible(painter)      # nothing while it is still theirs
        painter.restore()
        self.paint_handles(painter)

    def release_split(self) -> None:
        """A stroke of a split annotation changed: all of its strokes are
        drawn here from now on, and the page leaves the annotation out."""
        if not self.split_theirs:
            return
        frame = self.parentItem()
        siblings = [self]
        if frame is not None and hasattr(frame, "markups"):
            siblings = [i for i in frame.markups()
                        if getattr(i, "split_from", 0) == self.split_from]
        for item in siblings:
            item.split_theirs = False
            item.update()
        if frame is not None:
            frame.update()

    def sync_their_look(self) -> None:
        """Show the file's own drawing of this markup while it is unchanged,
        and nothing of it once it has been taken over."""
        # (a page that draws its file's markups with itself draws this one too)
        wanted = bool(self.still_theirs and self.from_annotation
                      and not getattr(self.parentItem(), "file_draws", False))
        if wanted and self._their_look is None:
            self._their_look = _TheirLook(self)
        if self._their_look is not None:
            self._their_look.prepareGeometryChange()
            self._their_look.setVisible(wanted)

    def paint_their_file(self, painter: QPainter, box=None) -> None:
        """On screen, a markup nobody has changed is drawn by its own file:
        its annotation alone, in squares the render processes draw, laid in
        its place among the other markups — so one taken over and moved does
        not suddenly cover those the file draws on top of it (Calcs.pdf,
        2026-10-01). The page itself is drawn without its markups."""
        frame = self.parentItem()
        page = getattr(frame, "page", None)
        if (page is None or not self.from_annotation or getattr(frame, "print_mode", False)
                or not getattr(page, "pdf_key", None) or page.pdf_page_index is None
                or not getattr(page, "pdf_annotations", True)
                or self.from_annotation not in set(page.markup_annotations or ())):
            return
        data = frame.document.asset(page.pdf_key)
        if not data:
            return
        from ..io import pdftiles
        from ..ui.scene import _draw_on_the_pixel_grid, _painted_scale

        to_page = self.sceneTransform() * frame.sceneTransform().inverted()[0]
        back, ok = to_page.inverted()
        if not ok:
            return
        if box is None:
            box = self.mapRectToParent(self.boundingRect()).adjusted(-12, -12, 12, 12)
        whole = frame.page_rect()
        tiles = pdftiles.TILES.annotation_tiles(
            page.pdf_key, data, int(page.pdf_page_index), whole, _painted_scale(painter),
            box, self.from_annotation, box)
        if not tiles:
            return
        painter.setWorldTransform(back * painter.worldTransform())
        for where, tile in tiles:
            _draw_on_the_pixel_grid(painter, where, tile)

    def paint_content(self, painter: QPainter) -> None:
        return

    def paint_visible(self, painter: QPainter) -> None:
        """Draw what this markup actually looks like.

        Nothing, while it is still somebody else's and their own file is
        drawing it. Everything that puts a markup anywhere — the canvas, a
        print, an export, a snapshot, the markups list — goes through here, so
        a markup read out of somebody's drawing looks the same in all of them.
        """
        if self.still_theirs:
            return
        if self.stamp_svg:
            self.paint_stamp_drawing(painter)
        elif self._their_picture is not None and self.picture_framed:
            self.paint_their_picture(painter)
            self.paint_content(painter)
        elif self._their_picture is not None:
            self.paint_their_picture(painter)
        else:
            region = self.hatch_region() if self.style.hatched() else None
            if region is None or region.isEmpty():
                self.paint_content(painter)
                return
            # Fill, then hatch, then the markup itself without its fill: the
            # hatch sits behind the outline, not over it.
            if self.style.fill:
                painter.save()
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.fillPath(region, self.style.brush())
                painter.restore()
            paint_hatch(painter, region, self.style)
            fill = self.style.fill
            self.style.fill = ""
            try:
                self.paint_content(painter)
            finally:
                self.style.fill = fill

    def hatch_region(self) -> Optional[QPainterPath]:
        """The area a hatch covers, in item coordinates; None for no hatch."""
        return None

    def paint_stamp_drawing(self, painter: QPainter) -> None:
        """Draw a stamp's kept SVG linework into its box, as vectors."""
        if self._stamp_renderer is None:
            from PySide6.QtCore import QByteArray
            from PySide6.QtSvg import QSvgRenderer
            self._stamp_renderer = QSvgRenderer(QByteArray(self.stamp_svg.encode()))
        box = (QRectF(*self.their_picture_box) if self.their_picture_box
               else self.local_rect())
        if not self._stamp_renderer.isValid() or box.isEmpty():
            return
        painter.save()
        painter.setOpacity(painter.opacity() * self.style.opacity)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.NoBrush)
        self._stamp_renderer.render(painter, box)
        painter.restore()

    def paint_their_picture(self, painter: QPainter) -> None:
        picture = self._their_picture
        box = (QRectF(*self.their_picture_box) if self.their_picture_box
               and not self.picture_framed else self.local_rect().normalized())
        if picture is None or picture.isNull() or box.isEmpty():
            return
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(box, picture, QRectF(picture.rect()))

    def load_from_document(self, document) -> None:
        """Anything this markup needs out of the document it belongs to."""
        if not self.their_picture_asset:
            return
        data = document.asset(self.their_picture_asset)
        if not data:
            return
        from PySide6.QtCore import QByteArray
        from PySide6.QtGui import QPixmap

        picture = QPixmap()
        if picture.loadFromData(QByteArray(data)) and not picture.isNull():
            self._their_picture = picture

    # -- somebody else's markup --------------------------------------------
    #
    # A markup read out of somebody else's PDF is drawn by that PDF, not by
    # this application, for exactly as long as nobody has changed it.
    #
    # Redrawing it here instead gets close and no closer. A Bluebeam stamp is
    # a logo and a ruled table; its section marks are filled to a shape
    # nothing here describes; its text is set by an appearance stream rather
    # than by the font its ``/DA`` happens to name. Close is worse than
    # useless on a drawing somebody is checking against the original — and
    # every version of "close" that has been tried, a redraw from the
    # dictionary and then a picture of the annotation, was soft, or wrong, or
    # both. The file's own drawing of it is neither: it is the same drawing
    # every other reader in the world shows, at every zoom, for nothing.
    #
    # So the page is rendered with those annotations still on it, and the
    # markup sitting over one draws nothing at all. It is still a markup — it
    # can be picked, moved, listed, measured, deleted — and it still goes back
    # into the file as the very annotation it came from, byte for byte.
    #
    # The moment it is really changed, that stops: the annotation is left out
    # of the page's render, this draws the markup itself, and it is written
    # back as one of ours. That is the one conversion, and it happens once.

    # -- groups ------------------------------------------------------------
    def set_group_path(self, path, outermost: str = "") -> None:
        """Say which groups this markup is inside, outermost first.

        *outermost* is what a document written before groups could nest says
        instead, and is used when there is no path.
        """
        steps = [str(step) for step in (path or ()) if str(step)]
        if not steps and outermost:
            steps = [outermost]
        self.group_path = tuple(steps)
        self.group = steps[0] if steps else ""

    def put_in_a_group(self, name: str) -> None:
        """Put this markup inside a new group, outside any it is already in."""
        self.set_group_path((name,) + tuple(
            step for step in self.group_path if step != name))

    def out_of_its_outer_group(self) -> None:
        """Take this markup out of the outermost group it is in.

        One layer at a time. A section mark is a bubble and its label inside
        the group that adds the cut line: ungrouping it should give back the
        cut line and the bubble-with-its-label, not five loose markups.
        """
        self.set_group_path(self.group_path[1:])

    def make_it_ours(self) -> None:
        """Take this markup over: from here it is drawn and saved as ours."""
        self.release_split()
        if self.still_theirs:
            self.still_theirs = False
            self.sync_their_look()
            if self.scene() is not None:
                self.scene().update()
            self.update()

    def itemChange(self, change, value):
        """Anything done to this markup takes it over.

        Moving especially. While it is still theirs it is their file drawing
        it, at the place their file has it — so a markup dragged across the
        sheet without changing hands would not appear to move at all. Being
        picked out does not count: a click, or the properties showing what it
        is, changes nothing, and the file goes on drawing it exactly as it
        was written (the user, 2026-10-01). Undoing the change that took it
        over gives it back to the file.
        """
        if change in _CHANGES_THAT_SHOW:
            self._changing()
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            # Picking a markup out changes nothing about its drawing, only
            # whether its handles show; the page draws those over its squares.
            frame = self.parentItem()
            if self in getattr(getattr(frame, "layer", None), "members", ()):
                frame.update(self.mapRectToParent(self.boundingRect()))
        elif change == QGraphicsItem.ItemParentChange:
            layer = self._layer()
            if layer is not None:
                layer.forget(self)
        elif change == QGraphicsItem.ItemParentHasChanged:
            self._changing()
        if change in (QGraphicsItem.ItemPositionHasChanged,
                      QGraphicsItem.ItemTransformHasChanged) \
                and (self.still_theirs or self.split_theirs) and not self._still_arriving:
            self.make_it_ours()
        return super().itemChange(change, value)

    @property
    def came_with_its_own_look(self) -> bool:
        return self.still_theirs

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

    def outline_path(self) -> QPainterPath:
        """The current closed host outline used to clip its cut-outs.

        Cut-outs keep the geometry that was drawn, but only their overlap with
        the host is effective.  Rebuilding this path on every paint/measure is
        what makes a hole follow a later resize instead of hanging outside it.
        """
        path = QPainterPath()
        ring = self.outline_ring()
        if len(ring) >= 3:
            path.addPolygon(QPolygonF(ring))
            path.closeSubpath()
        return path

    def clipped_holes_path(self) -> QPainterPath:
        """The portion of all saved cut-outs that is still inside the host."""
        holes = self.holes_path()
        outline = self.outline_path()
        if holes.isEmpty() or outline.isEmpty():
            return QPainterPath()
        return holes.intersected(outline)

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
        painter.drawPath(self.clipped_holes_path())
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
            "from_drawing": self.from_drawing,
            "created": self.created,
            "modified": self.modified,
            "locked": self.locked,
            "printable": self.printable,
            "hidden": self.hidden,
            "flattened": self.flattened,
            "from_annotation": self.from_annotation,
            "still_theirs": self.still_theirs,
            "split_from_annotation": self.split_from,
            "split_theirs": self.split_theirs,
            "their_box": list(self.their_box) if self.still_theirs else [],
            "their_picture_asset": self.their_picture_asset,
            "picture_framed": self.picture_framed,
            "their_picture_box": list(self.their_picture_box),
            "stamp_picture": self._stamp_picture_b64,
            "stamp_svg": self.stamp_svg,
            "flatten_recoverable": self.flatten_recoverable,
            "locked_before_flatten": self.locked_before_flatten,
            "group": self.group,
            "group_path": list(self.group_path),
            "group_title": self.group_title,
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
        self.set_group_path(data.get("group_path") or (),
                            str(data.get("group", "")))
        self.group_title = str(data.get("group_title", "") or "")
        self.author = data.get("author", "")
        self.subject = data.get("subject", "")
        self.comment = data.get("comment", "")
        self.label = data.get("label", "")
        # Documents written while this was a layer rather than a flag say so
        # the old way, and still open.
        self.from_drawing = bool(data.get("from_drawing",
                                          data.get("layer") == "Drawing"))
        self.created = data.get("created", self.created)
        self.modified = data.get("modified", self.modified)
        self.printable = bool(data.get("printable", True))
        self.hidden = bool(data.get("hidden", False))
        self.from_annotation = int(data.get("from_annotation", 0) or 0)
        self.still_theirs = bool(data.get("still_theirs", False))
        self.split_from = int(data.get("split_from_annotation", 0) or 0)
        self.split_theirs = bool(data.get("split_theirs", False)) and bool(self.split_from)
        found_box = data.get("their_box") or ()
        self.their_box = tuple(float(v) for v in found_box) if len(found_box) == 4 else ()
        self.their_picture_asset = str(data.get("their_picture_asset", ""))
        self.picture_framed = bool(data.get("picture_framed", False))
        found = data.get("their_picture_box") or ()
        self.their_picture_box = tuple(float(v) for v in found) \
            if len(found) == 4 else ()
        svg = data.get("stamp_svg", "")
        if isinstance(svg, str) and svg:
            from ..io.pdfsnapshot import inline_glyphs
            self.stamp_svg = inline_glyphs(svg)
            self._stamp_renderer = None
        b64 = data.get("stamp_picture", "")
        if isinstance(b64, str) and b64:
            self._stamp_picture_b64 = b64
            try:
                import base64
                from PySide6.QtCore import QByteArray
                from PySide6.QtGui import QPixmap
                picture = QPixmap()
                if picture.loadFromData(QByteArray(base64.b64decode(b64))) \
                        and not picture.isNull():
                    self._their_picture = picture
            except Exception:
                pass
        self.flattened = bool(data.get("flattened", False))
        self.flatten_recoverable = bool(data.get("flatten_recoverable", True))
        self.locked_before_flatten = bool(data.get("locked_before_flatten", False))
        # The page's own line work is never dragged about: it is the drawing,
        # not a markup on it. It is worth catching hold of and pointing at,
        # which is why it is here at all, but picking a beam up and moving it
        # is not something anybody meant to do.
        self.set_locked(bool(data.get("locked", False)) or self.flattened
                        or self.from_drawing)
        if self.flattened:
            self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        if self.hidden:
            self.setVisible(False)
        # Rotation is always about the visible object's centre.  Keeping the
        # origin implicit at (0, 0) made a reopened rotated object orbit away
        # from the position stored in the document.
        self.setTransformOriginPoint(self.local_rect().center())
        self.setRotation(float(data.get("rotation", 0)))
        self.sync_their_look()

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


def round_the_joins(painter: QPainter) -> None:
    """Draw what comes next with round joins — for a cloud's scallops.

    Where one scallop meets the next the line turns back on itself, and a
    mitred join there throws a spike inward. How far the spike reaches
    depends on the renderer's miter limit, so the screen drew spikes the
    exported PDF did not: the same cloud, looking different in two places.
    Round joins look the same everywhere, and are how a cloud is drawn.
    """
    pen = painter.pen()
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)


def cloud_path(polygon: QPolygonF, radius: float, closed: bool = True) -> QPainterPath:
    """Convert a polyline into a Bluebeam-style revision cloud."""
    key = (tuple((point.x(), point.y()) for point in polygon), radius, closed)
    made = _CLOUDS.get(key)
    if made is None:
        made = _cloud_path(polygon, radius, closed)
        if len(_CLOUDS) > 2048:
            _CLOUDS.clear()
        _CLOUDS[key] = made
    return QPainterPath(made)


#: Clouds and pens already worked out: the same cloud is drawn again on every
#: repaint and into every square it crosses.
_CLOUDS: dict = {}
_PENS: dict = {}


def _cloud_path(polygon: QPolygonF, radius: float, closed: bool = True) -> QPainterPath:
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


class _TheirLook(QGraphicsItem):
    """The file's own drawing of a markup nobody has changed, in the box the
    file gives it (/Rect) — not the box this application would measure:
    Bluebeam puts a dimension's words out at the end of a leader, and drawn
    inside the markup's own box "1m" was cut away (the user, 2026-10-01).
    It belongs to its markup, so it is stacked with it among the others; it
    takes no clicks, and goes the moment the markup is changed."""

    MARKUP_LOOK = True
    _baked_rect = None

    def __init__(self, markup):
        super().__init__(markup)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setAcceptHoverEvents(False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsFocusable, False)

    def _page_box(self) -> QRectF:
        markup = self.parentItem()
        if markup.their_box:
            return QRectF(*markup.their_box)
        return markup.mapRectToParent(markup.boundingRect()).adjusted(-12, -12, 12, 12)

    def boundingRect(self) -> QRectF:
        if self._baked_rect is not None:
            return self._baked_rect
        markup = self.parentItem()
        if markup is None or markup.parentItem() is None:
            return QRectF()
        return markup.mapRectFromParent(self._page_box()).adjusted(-2, -2, 2, 2)

    def shape(self):
        from PySide6.QtGui import QPainterPath
        return QPainterPath()                      # nothing to click on

    def paint(self, painter: QPainter, option, widget=None) -> None:
        markup = self.parentItem()
        if markup is None or not markup.still_theirs:
            return
        engine = painter.paintEngine()
        if (markup.style.blend == "multiply" and engine is not None
                and engine.type() == engine.Type.OpenGL2):
            return                     # the page draws it (markups_drawn_alone)
        painter.save()
        markup.apply_blend(painter)
        markup.paint_their_file(painter, self._page_box().adjusted(-1, -1, 1, 1))
        painter.restore()
