"""Common infrastructure for every object that can live on a page."""
from __future__ import annotations

import math
import uuid
import weakref
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
#
# Revu's own come first, in its order and by its names (the user's Revu 21
# line-style list, 2026-10-18): Solid, Dashed 1 to 6 as its samples draw
# them, then its complex styles — lines with symbols, labels, loops or a
# second line, drawn by items/complexlines.py, which have no dashes of their
# own. CalcForge's own dash styles follow, under the keys files already use.
DASH_ARRAYS = {
    "solid": [],
    "dashed 1": [3.0, 2.25],
    "dashed 2": [4.0, 4.0],
    "dashed 3": [5.5, 5.25],
    "dashed 4": [5.5, 3.75, 3.0, 3.75],
    "dashed 5": [5.5, 3.75, 21.75, 3.75],
    "dashed 6": [10.5, 5.25, 6.0, 5.25],
    "fenceline circle": [],
    "fenceline square": [],
    "gas": [],
    "hot water": [],
    "zig zag": [],
    "insulation": [],
    "double": [],
    "tracks": [],
    "road": [],
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


ARROW_HEADS = ["none", "open", "arrow", "open_reversed", "closed_reversed", "butt",
               "diamond", "dot", "square", "slash", "half"]
# Bluebeam's names for the line ends (its Start and End lists, in its order);
# "half" is CalcForge's own, a one-sided head
ARROW_NAMES = {"none": "None", "open": "Open", "arrow": "Closed",
               "open_reversed": "Open (Reversed)", "closed_reversed": "Closed (Reversed)",
               "butt": "Butt", "diamond": "Diamond", "dot": "Round", "square": "Square",
               "slash": "Slash", "half": "Half Arrow"}
# the ends that are filled; the others are strokes only
FILLED_HEADS = {"arrow", "closed_reversed", "diamond", "dot", "square"}

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
    # Revu's other Font Styles: struck through, and the words set above or
    # below the line (a whole box's; a run's own is in its rich text).
    strikethrough: bool = False
    superscript: bool = False
    subscript: bool = False
    # Revu's "A" beside the font size: the words set at the largest size
    # that fits the box, worked out again as the box or the words change.
    font_auto: bool = False
    text_color: str = "#111318"
    align: str = "left"
    valign: str = "top"
    arrow_start: str = "none"
    arrow_end: str = "none"
    arrow_size: float = 1.0
    # The start's own size, as Revu sizes each end on its own. 0 means the
    # same as the end's (arrow_size): how every markup was before.
    arrow_start_size: float = 0.0
    # Revu's line-end colour (a line's Fill Color): what a filled end —
    # Closed, Round, Square, Diamond — is filled with. Empty follows the
    # line's colour, as every markup was before it had one; "none" leaves
    # the ends hollow. Written to the PDF as a line's /IC.
    end_fill: str = ""
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
        font = page_font(self.font_family, self.font_size, self.bold, self.italic,
                         self.underline)
        if self.strikethrough:
            font.setStrikeOut(True)
        return font

    #: Revu's Font Style toggles, in its order.
    FONT_STYLES = ("bold", "italic", "underline", "strikethrough", "superscript",
                   "subscript")

    def set_font_style(self, name: str, on: bool) -> None:
        """Turn one Font Style on or off. Superscript and subscript are one
        or the other, as Revu's are."""
        setattr(self, name, bool(on))
        if on and name == "superscript":
            self.subscript = False
        elif on and name == "subscript":
            self.superscript = False

    def start_size(self) -> float:
        """The start's line-end size: its own, or the end's when it has none."""
        own = float(self.arrow_start_size or 0.0)
        return own if own > 0 else float(self.arrow_size or 1.0)

    def end_fill_colour(self) -> str:
        """The colour a filled line end is filled with: its own, or the
        line's when it has none of its own; "" when the ends are hollow."""
        if self.end_fill == "none":
            return ""
        return self.end_fill or self.stroke or ""

    def end_brush(self) -> QBrush:
        """The brush a filled line end is drawn with (the markup's opacity)."""
        if self.end_fill == "none":
            return QBrush(Qt.NoBrush)
        made = QColor(self.end_fill_colour() or "#000000")
        made.setAlphaF(max(0.0, min(1.0, self.opacity)))
        return QBrush(made)

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
# Bluebeam's selection colours (from its manual's screenshots): the dashed
# boxes and the scale handles blue, control points gold, rotation blue
SELECT_BLUE = QColor("#2a7dbe")
CONTROL_GOLD = QColor("#d1b53a")
ROTATE_BLUE = QColor("#3987c2")


#: The smallest zoom any view is showing the pages at (ui/view.py keeps it):
#: handles are drawn a fixed number of pixels across, so the further out the
#: view, the more of the page they cover.
_CHROME_ZOOM = [1.0]


def note_view_zoom(scene) -> None:
    """A view of *scene* zoomed: the selected markups' handles change size,
    and with them the room each markup says it paints in."""
    if scene is None:
        return
    zooms = [max(math.hypot(view.transform().m11(), view.transform().m12()), 0.01)
             for view in scene.views()]
    zoom = min(zooms) if zooms else 1.0
    if abs(zoom - _CHROME_ZOOM[0]) < 1e-9:
        return
    _CHROME_ZOOM[0] = zoom
    for item in scene.selectedItems():
        if isinstance(item, MarkupItem):
            item._may_leave_its_page()
            QGraphicsObject.prepareGeometryChange(item)


def covered_rect(item) -> QRectF:
    """What a markup covers on its page, in its parent's coordinates — not
    the room its selection handles take (an export, a picture of the
    selection, a snapshot)."""
    if hasattr(item, "bounds_without_chrome"):
        return item.mapRectToParent(item.bounds_without_chrome())
    return item.mapRectToParent(item.boundingRect())


def many_selected(scene) -> bool:
    """True when the selection is several things (Revu's multi-selection).

    Each markup still shows and uses its own control points (a handle
    resizes its own markup only); a press anywhere else on any of them moves
    them all (ui/view.py). There is no box round the lot (the user,
    2026-10-16: group resize is not Bluebeam's)."""
    ask = getattr(scene, "many_selected", None) if scene is not None else None
    return bool(ask()) if callable(ask) else False


#: Half the width of each kind of handle as it is drawn, in screen pixels: a
#: press counts as on a handle only inside the square it is drawn in.
CONTROL_HALF_PX = (HANDLE_SCREEN_PX + 1.0) / 2      # a gold control point
SQUARE_HALF_PX = (HANDLE_SCREEN_PX + 1.5) / 2       # a scale-box corner, rotation
LEADER_HALF_PX = HANDLE_SCREEN_PX / 2 + 1.0         # a leader's diamond


def view_zoom(item) -> float:
    """How many screen pixels one of *item*'s own units is, in its view."""
    scene = item.scene() if item is not None else None
    views = scene.views() if scene is not None else []
    if views:
        shape = views[0].transform()
        zoom = math.hypot(shape.m11(), shape.m12())
    else:
        zoom = _CHROME_ZOOM[0]
    own = item.sceneTransform()
    return max(zoom * math.hypot(own.m11(), own.m12()), 0.01)


def handle_zoom(painter: QPainter) -> float:
    shape = painter.transform()
    return max(math.hypot(shape.m11(), shape.m12()), 0.01)


#: The pens and brushes the handles are drawn with, by colour and zoom. Four
#: hundred markups picked out are thousands of handles a frame, and making
#: each one's pen and brush afresh was a good part of drawing it (QA,
#: 2026-10-15). Shared: whoever is given one sets it, and never changes it.
_HANDLE_TOOLS: dict = {}


def _handle_tools(colour: QColor, darker: int, width: float) -> tuple:
    """(pen, brush) for a handle filled with *colour*, edged darker."""
    key = (colour.rgba(), darker, width)
    found = _HANDLE_TOOLS.get(key)
    if found is None:
        if len(_HANDLE_TOOLS) > 256:
            _HANDLE_TOOLS.clear()        # the zooms of a while ago
        found = _HANDLE_TOOLS[key] = (QPen(colour.darker(darker), width), QBrush(colour))
    return found


def selection_pen(zoom: float) -> QPen:
    key = ("selection", zoom)
    pen = _HANDLE_TOOLS.get(key)
    if pen is None:
        if len(_HANDLE_TOOLS) > 256:
            _HANDLE_TOOLS.clear()
        pen = QPen(SELECT_BLUE)
        pen.setWidthF(0.7 / zoom)
        pen.setStyle(Qt.DashLine)
        _HANDLE_TOOLS[key] = pen
    return pen


def paint_control_point(painter: QPainter, point: QPointF, zoom: float,
                        colour: QColor = CONTROL_GOLD) -> None:
    """A control point: a gold dot, as Bluebeam's."""
    radius = (HANDLE_SCREEN_PX + 1.0) / zoom / 2
    pen, brush = _handle_tools(colour, 160, 0.7 / zoom)
    painter.setPen(pen)
    painter.setBrush(brush)
    painter.drawEllipse(point, radius, radius)


def paint_rotate_handle(painter: QPainter, point: QPointF, stalk: QPointF, zoom: float) -> None:
    """Bluebeam's rotation handle: a blue dot on a dashed stalk."""
    painter.setPen(selection_pen(zoom))
    painter.drawLine(point, stalk)
    radius = (HANDLE_SCREEN_PX + 1.5) / zoom / 2
    pen, brush = _handle_tools(ROTATE_BLUE, 150, 0.7 / zoom)
    painter.setPen(pen)
    painter.setBrush(brush)
    painter.drawEllipse(point, radius, radius)
ROTATE_OFFSET = 22.0

CORNER_HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")

HANDLE_CURSORS = {
    # The eight corners and edges resize, and the pointer says which way.
    "nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
    "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
    "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
    "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
    # Revu's scale box: its corners resize the whole markup, diagonally.
    "scale_nw": Qt.SizeFDiagCursor, "scale_se": Qt.SizeFDiagCursor,
    "scale_ne": Qt.SizeBDiagCursor, "scale_sw": Qt.SizeBDiagCursor,
    # A call-out's arrow heads and hinges are numbered — l0, e0, l1, e1 —
    # because there is no limit to how many a comment may need, so they are
    # matched by their shape below rather than listed here.
    # A measurement's own words: dragged to move them, turned to angle them.
    "lbl": Qt.SizeAllCursor,
    "lbltext": Qt.SizeAllCursor,
}

#: The handles that turn a markup, which get Revu's curled arrow.
ROTATE_HANDLES = ("rot", "lblrot")
_ROTATE_CURSOR = None


def rotate_cursor():
    """Revu's rotation pointer: three quarters of a circle with an arrowhead,
    black on a white halo so it shows on any drawing. Made on first use, as a
    cursor needs the application running."""
    global _ROTATE_CURSOR
    if _ROTATE_CURSOR is None:
        from PySide6.QtGui import QCursor, QPixmap
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        arc = QPainterPath()
        arc.arcMoveTo(QRectF(5, 5, 14, 14), 90)
        arc.arcTo(QRectF(5, 5, 14, 14), 90, 270)
        head = QPolygonF([QPointF(11, 2), QPointF(15.5, 5), QPointF(11, 8)])
        for colour, width in (("#ffffff", 4.0), ("#000000", 1.6)):
            painter.setPen(QPen(QColor(colour), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(arc)
            painter.setBrush(QColor(colour))
            painter.drawPolygon(head)
        painter.end()
        _ROTATE_CURSOR = QCursor(pixmap, 12, 12)
    return _ROTATE_CURSOR


def cursor_for_handle(key: str):
    """The pointer for a handle, including the numbered ones.

    A polyline has as many handles as it has corners — v0, v1, v2 — so they
    cannot be listed one by one. Every one of them moves a point, which is
    what the pointing hand means everywhere else in the app.
    """
    if key in ROTATE_HANDLES:
        return rotate_cursor()
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

#: The pictures of their files' markups read so far, by document and asset:
#: (the asset's bytes, the picture) — see MarkupItem.load_from_document.
_PICTURES_READ: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()

#: What changes how a markup looks on its page, before it happens.
_CHANGES_THAT_SHOW = (QGraphicsItem.ItemPositionChange, QGraphicsItem.ItemTransformChange,
                      QGraphicsItem.ItemRotationChange, QGraphicsItem.ItemScaleChange,
                      QGraphicsItem.ItemTransformOriginPointChange,
                      QGraphicsItem.ItemZValueChange,
                      QGraphicsItem.ItemVisibleChange, QGraphicsItem.ItemEnabledChange,
                      QGraphicsItem.ItemChildAddedChange, QGraphicsItem.ItemChildRemovedChange)


class MarkupItem(QGraphicsObject):
    #: dimmed on the canvas because the Markups List's filter leaves it out
    #: (ui/filterdim.py); the canvas's alone, never saved or printed
    filter_dimmed = False
    """Base class: selection handles, style, metadata and serialisation."""

    TYPE = "markup"
    NAME = "Markup"
    RESIZABLE = True
    # A cloud's Size, as Bluebeam's: no unit — it is the PDF's cloudy-border
    # intensity (/BE /I), so every reader draws the same scallops from it —
    # and Invert, the scallops turned inward. Only clouds use them.
    cloud_size: float = 2.0
    cloud_invert: bool = False

    @property
    def cloud_radius(self) -> float:
        """The scallops' radius in points, from the Size and the line width."""
        return cloud_radius_for(self.cloud_size, self._cloud_line_width())

    @cloud_radius.setter
    def cloud_radius(self, radius: float) -> None:
        self.cloud_size = cloud_size_for(float(radius), self._cloud_line_width())

    def _cloud_line_width(self) -> float:
        style = getattr(self, "style", None)
        return float(getattr(style, "width", 0.0) or 0.0)

    def cloud_to_dict(self, data: dict) -> None:
        data["cloud_size"] = round(float(self.cloud_size), 6)
        if self.cloud_invert:
            data["cloud_invert"] = True

    def cloud_from_dict(self, data: dict) -> None:
        """After the style is read: a record from before Size (2026-10-14)
        gave the radius in points, turned into the Size that draws it the same."""
        if "cloud_size" in data:
            self.cloud_size = float(data["cloud_size"])
        elif "cloud_radius" in data:
            self.cloud_radius = float(data["cloud_radius"])
        else:
            self.cloud_size = CLOUD_SIZE
        self.cloud_invert = bool(data.get("cloud_invert", False))
    ROTATABLE = True
    HAS_TEXT = False

    geometryChanged = Signal()
    contentChanged = Signal()

    #: While this markup is drawn from its page's squares (ui/markuplayer.py),
    #: its size as it was when it went in: it is not changing, and Qt asks
    #: for it twice per markup per frame.
    _baked_rect = None

    #: Its size, worked out once, for a markup still exactly as its file
    #: wrote it: Qt asks every markup on the canvas for it several times a
    #: frame, a few dozen Python calls each time (2026-10-08), and one still
    #: its file's cannot change without being taken over first — which ends
    #: this. (A markup of ours is asked afresh: some of the ways it is resized
    #: only repaint the view.)
    _bounds = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        own = cls.__dict__.get("boundingRect")
        if own is not None and not getattr(own, "_answers_baked", False):
            def boundingRect(self, _own=own):
                baked = self._baked_rect
                if baked is not None:
                    return baked
                self._bounding_depth += 1
                try:
                    if not (self.still_theirs or self.split_theirs):
                        found = _own(self)
                    else:
                        found = self._bounds
                        if found is None:
                            found = _own(self)
                            if self.parentItem() is not None:
                                self._bounds = found
                finally:
                    self._bounding_depth -= 1
                return self._with_chrome(found)
            boundingRect._answers_baked = True
            boundingRect.__doc__ = own.__doc__
            cls.boundingRect = boundingRect

    # -- the page's squares (ui/markuplayer.py) ------------------------------
    def _layer(self):
        return getattr(self.parentItem(), "layer", None)

    def _changing(self) -> None:
        self._bounds = None
        layer = self._layer()
        if layer is not None:
            layer.touched(self)
        self._may_leave_its_page()

    def _may_leave_its_page(self) -> None:
        """Its page stops telling Qt its markups all stay inside it, until
        this one has been still a moment (PageFrame.markups_may_have_moved)."""
        holder = self.parentItem()
        while holder is not None and not hasattr(holder, "markups_may_have_moved"):
            holder = holder.parentItem()
        if holder is not None:
            holder.markups_may_have_moved()

    def update(self, *args):                 # (no annotation: a Qt slot)
        self._changing()
        super().update(*args)

    def prepareGeometryChange(self):
        self._changing()
        super().prepareGeometryChange()
        # Qt reads the old size in there; the new one is read fresh after
        self._bounds = None

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
        #: an ink annotation's whole drawing by its file, on its first stroke,
        #: while the Markups List's filter dims it (filterdim.py)
        self._whole_look = None
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
        if not (self.still_theirs or self.split_theirs):
            return self._with_chrome(self._bounds_now())
        known = self._bounds
        if known is None:
            known = self._bounds_now()
            if self.parentItem() is not None:
                self._bounds = known
        return self._with_chrome(known)

    #: How deep in a chain of boundingRect calls (a subclass's asking its
    #: parent class's): only the outermost adds the handles' room.
    _bounding_depth = 0

    def chrome_room(self) -> float:
        """The room its handles take at the current zoom, selected or not."""
        return (2 * HANDLE_SCREEN_PX + 8.0) / max(_CHROME_ZOOM[0], 0.01) + 6.0

    def chrome_margin(self) -> float:
        """How far round itself a selected markup paints its handles.

        The handles are a fixed number of pixels across at any zoom, so in
        the page's units they grow as the view zooms out. Left out of the
        markup's own rectangle, Qt never repaints where they were, and moving
        the markup left pieces of its selection box and its rotation handle
        behind (the user, 2026-10-14)."""
        if not self.isSelected() or self.group:
            return 0.0
        return self.chrome_room()

    def _with_chrome(self, rect: QRectF) -> QRectF:
        if self._bounding_depth:
            return rect                      # a subclass asked: it adds it
        margin = self.chrome_margin()
        return rect.adjusted(-margin, -margin, margin, margin) if margin else rect

    def bounds_without_chrome(self) -> QRectF:
        """The markup's rectangle without its handles' room: what it covers."""
        rect = self.boundingRect()
        margin = self.chrome_margin()
        return rect.adjusted(margin, margin, -margin, -margin) if margin else rect

    def _bounds_now(self) -> QRectF:
        from .complexlines import reach
        # a Double, Tracks or Road line reaches past its pen
        margin = self.style.width + HANDLE_SIZE + 4 + reach(self.style)
        box = self.local_rect().normalized().adjusted(-margin, -margin, margin, margin)
        if self.ROTATABLE:
            # The rotation handle stands off above the box. Left out of here it
            # is painted outside the item's own rectangle, so Qt clips it and
            # leaves a smear of it behind every time the markup moves.
            box.setTop(box.top() - ROTATE_OFFSET - HANDLE_SIZE)
        return self._with_scale_box(box)

    def _with_scale_box(self, box: QRectF) -> QRectF:
        """*box* grown to hold the scale box and the rotation handle above it."""
        if not self.has_scale_box():
            return box
        outer = self.scale_box().adjusted(-HANDLE_SIZE - 2, -HANDLE_SIZE - 2,
                                          HANDLE_SIZE + 2, HANDLE_SIZE + 2)
        if self.ROTATABLE or getattr(self, "kind", "") in ("polyline", "polygon", "cloud"):
            outer.setTop(outer.top() - ROTATE_OFFSET - HANDLE_SIZE)
        return box.united(outer)

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
            # above the scale box when there is one, as Bluebeam's
            top = self.scale_box().top() if self.has_scale_box() else rect.top()
            points["rot"] = QPointF(rect.center().x(), top - ROTATE_OFFSET)
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

    # Bluebeam's scale box: a dashed box round everything drawn, its four
    # corners handles that scale the markup in proportion (Shift frees the
    # proportions). Shapes, pictures and snapshots have one.
    SCALE_BOX = False

    def has_scale_box(self) -> bool:
        return self.SCALE_BOX and self.RESIZABLE and not self.locked

    def scale_box(self) -> QRectF:
        """The scale box: what is drawn, and a little room round it."""
        rect = self.local_rect().normalized()
        pad = max(float(getattr(self.style, "width", 0.0) or 0.0), 0.0) / 2 + 3.0
        if getattr(self, "kind", "") == "cloud" or getattr(self, "shape_kind", "") == "cloud":
            pad += self.cloud_radius
        return rect.adjusted(-pad, -pad, pad, pad)

    def scale_points(self) -> dict[str, QPointF]:
        if not self.has_scale_box():
            return {}
        box = self.scale_box()
        return {"scale_nw": box.topLeft(), "scale_ne": box.topRight(),
                "scale_se": box.bottomRight(), "scale_sw": box.bottomLeft()}

    def handle_half_px(self, key: str) -> float:
        """Half the drawn size of handle *key*, in screen pixels."""
        if key == "rot" or key.startswith("scale_"):
            return SQUARE_HALF_PX
        if key in self.leader_handles():
            return LEADER_HALF_PX
        return CONTROL_HALF_PX

    def handle_at(self, local_pos: QPointF, tolerance: Optional[float] = None,
                  zoom: Optional[float] = None) -> Optional[str]:
        """The handle under *local_pos*. A handle takes the press only inside
        the square it is drawn in (QA finding 1.7: a reach of 4 pt round every
        point covered nearly the whole stroke of a small markup, so pressing
        its edge resized it instead of moving the selection)."""
        if self.locked:
            return None
        if tolerance is None:
            zoom = zoom if zoom else view_zoom(self)
        # the nearest within reach: a shape's corner and its scale-box corner
        # can both be in reach of one click
        best, best_distance = None, None
        for key, point in list(self.handle_points().items()) + list(self.scale_points().items()):
            dx, dy = abs(point.x() - local_pos.x()), abs(point.y() - local_pos.y())
            reach = tolerance if tolerance is not None else self.handle_half_px(key) / zoom
            if dx <= reach and dy <= reach:
                distance = dx * dx + dy * dy
                if best_distance is None or distance < best_distance:
                    best, best_distance = key, distance
        return best

    def drag_handle(self, key: str, local_pos: QPointF, keep_ratio: bool = False) -> None:
        """A handle dragged to *local_pos*: a scale-box corner scales the
        markup about the opposite corner, in proportion unless Shift is held
        (Bluebeam's; for a scale-box corner *keep_ratio* is whether Shift is
        held); any other handle is the markup's own."""
        if not key.startswith("scale_"):
            self.move_handle(key, local_pos, keep_ratio)
            return
        rect = self.local_rect().normalized()
        box = self.scale_box()
        corner = key[len("scale_"):]
        # The corner of the markup's own box opposite the one dragged stays
        # where it is. Scaling about the scale box's corner instead — which
        # stands a few points off the markup — moved the markup by a little
        # with every step of the drag (the user, 2026-10-19: "the image moved
        # while resizing").
        across = -1.0 if "w" in corner else 1.0
        down = -1.0 if "n" in corner else 1.0
        anchor = QPointF(rect.right() if across < 0 else rect.left(),
                         rect.bottom() if down < 0 else rect.top())
        pad_x = (rect.left() - box.left()) if across < 0 else (box.right() - rect.right())
        pad_y = (rect.top() - box.top()) if down < 0 else (box.bottom() - rect.bottom())
        wide, high = max(rect.width(), 1e-6), max(rect.height(), 1e-6)
        # the box's corner under the pointer: the markup's corner a pad in
        sx = ((local_pos.x() - anchor.x()) * across - pad_x) / wide
        sy = ((local_pos.y() - anchor.y()) * down - pad_y) / high
        if not keep_ratio:
            sx = sy = max(sx, sy)
        sx, sy = max(sx, 0.02), max(sy, 0.02)
        width, height = rect.width() * sx, rect.height() * sy
        if width < 2 or height < 2:
            return
        self._resize_to(self._box_from(anchor, across, down, width, height))

    def move_handle(self, key: str, local_pos: QPointF, keep_ratio: bool = False) -> None:
        rect = self.local_rect().normalized()
        if key == "rot":
            centre = rect.center()
            angle = math.degrees(math.atan2(local_pos.y() - centre.y(),
                                            local_pos.x() - centre.x())) + 90
            angle = round(angle / (15 if keep_ratio else 1)) * (15 if keep_ratio else 1)
            self.set_item_rotation(angle)
            return
        if keep_ratio and rect.width() > 0 and rect.height() > 0 \
                and key in ("nw", "ne", "se", "sw"):
            # In proportion, about the opposite corner, which stays put: the
            # size the pointer asks for along whichever way it has gone
            # further. (Only the width was read, and the height was then set
            # from the top down — so dragging a top corner moved the bottom
            # of the markup, and the markup with it.)
            across = -1.0 if "w" in key else 1.0
            down = -1.0 if "n" in key else 1.0
            anchor = QPointF(rect.right() if across < 0 else rect.left(),
                             rect.bottom() if down < 0 else rect.top())
            scale = max((local_pos.x() - anchor.x()) * across / rect.width(),
                        (local_pos.y() - anchor.y()) * down / rect.height())
            scale = max(scale, 2.0 / rect.width(), 2.0 / rect.height())
            self._resize_to(self._box_from(anchor, across, down,
                                           rect.width() * scale, rect.height() * scale))
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
        # too small: kept the least size from the side that is not moving
        if new_rect.width() < 2:
            if "w" in key:
                new_rect.setLeft(new_rect.right() - 2)
            else:
                new_rect.setWidth(2)
        if new_rect.height() < 2:
            if "n" in key:
                new_rect.setTop(new_rect.bottom() - 2)
            else:
                new_rect.setHeight(2)
        self._resize_to(new_rect)

    @staticmethod
    def _box_from(anchor: QPointF, across: float, down: float,
                  width: float, height: float) -> QRectF:
        """The box with a corner at *anchor*, reaching *width* by *height*
        the way *across* and *down* (each 1 or -1) point."""
        return QRectF(QPointF(anchor.x(), anchor.y()),
                      QPointF(anchor.x() + across * width,
                              anchor.y() + down * height)).normalized()

    def _resize_to(self, new_rect: QRectF) -> None:
        """Give the markup its new box, keeping it where it is on the page."""
        self.prepareGeometryChange()
        self.set_local_rect(new_rect)
        self._turn_about_centre()
        self.touch()
        self.geometryChanged.emit()

    def _turn_about_centre(self) -> None:
        """A turned markup turns about the middle of its box: once its box has
        been resized, about the new middle — with its place on the page
        exactly as it was. It is saved, undone and reopened turning about its
        middle, so left turning about the old one it came back from any of
        those somewhere else."""
        if not self.rotation() or hasattr(self, "show_upright"):
            return
        centre = self.local_rect().center()
        if self.transformOriginPoint() == centre:
            return
        was = self.mapToParent(QPointF(0, 0))
        self.setTransformOriginPoint(centre)
        self.setPos(self.pos() + was - self.mapToParent(QPointF(0, 0)))

    def paint_handles(self, painter: QPainter) -> None:
        """Bluebeam's selection: the shape's box dashed in blue, gold control
        points, the blue scale box round it all with square corners, and the
        rotation handle a blue dot on a dashed stalk above."""
        if not self.isSelected() or not self._handles_visible:
            return
        if self.group:
            return
        if self.locked:
            self.paint_locked_selection(painter)
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        zoom = handle_zoom(painter)
        rect = self.local_rect().normalized()
        painter.setPen(selection_pen(zoom))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
        self.paint_scale_box(painter, zoom)
        points = self.handle_points()
        leader = self.leader_handles()
        dots = self.control_dots()
        for key, point in points.items():
            if key == "rot":
                top = self.scale_box().top() if self.has_scale_box() else rect.top()
                paint_rotate_handle(painter, point, QPointF(rect.center().x(), top), zoom)
            elif key in dots:
                paint_control_point(painter, point, zoom, colour=SELECT_BLUE)
            elif key in leader:
                half = HANDLE_SCREEN_PX / zoom / 2
                painter.setPen(QPen(QColor(200, 90, 20), 0.6 / zoom))
                painter.setBrush(QBrush(QColor(255, 170, 80)))
                painter.drawPolygon(QPolygonF([
                    QPointF(point.x(), point.y() - half - 1.0 / zoom),
                    QPointF(point.x() + half + 1.0 / zoom, point.y()),
                    QPointF(point.x(), point.y() + half + 1.0 / zoom),
                    QPointF(point.x() - half - 1.0 / zoom, point.y())]))
            else:
                paint_control_point(painter, point, zoom)
        painter.restore()

    def paint_locked_selection(self, painter: QPainter) -> None:
        """A locked markup, selected: the dashed box stood off the shape, so
        it is not lost in the shape's own line, and a padlock on its corner —
        no handles, because nothing about it can be dragged (exercise round
        1, F-32: it showed no sign of being selected at all)."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        zoom = handle_zoom(painter)
        margin = (3.0 + 0.0) / zoom + max(float(getattr(self.style, "width", 0.0)), 0.0) / 2
        box = self.local_rect().normalized().adjusted(-margin, -margin, margin, margin)
        painter.setPen(selection_pen(zoom))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(box)
        # the padlock, a few pixels across whatever the zoom
        unit = 1.0 / zoom
        corner = box.topRight()
        body = QRectF(corner.x() - 4.5 * unit, corner.y() - 3.5 * unit, 9 * unit, 7 * unit)
        shackle = QRectF(body.x() + 1.8 * unit, body.y() - 4.2 * unit, 5.4 * unit, 7 * unit)
        pen = QPen(SELECT_BLUE)
        pen.setWidthF(1.3 * unit)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(shackle, 0, 180 * 16)
        painter.setPen(QPen(SELECT_BLUE, 0.8 * unit))
        painter.setBrush(QBrush(SELECT_BLUE))
        painter.drawRoundedRect(body, 1.2 * unit, 1.2 * unit)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawEllipse(QPointF(body.center().x(), body.center().y()), 1.1 * unit, 1.1 * unit)
        painter.restore()

    def paint_scale_box(self, painter: QPainter, zoom: float) -> None:
        if not self.has_scale_box():
            return
        box = self.scale_box()
        painter.setPen(selection_pen(zoom))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(box)
        size = (HANDLE_SCREEN_PX + 1.5) / zoom
        pen, brush = _handle_tools(SELECT_BLUE, 130, 0.6 / zoom)
        painter.setPen(pen)
        painter.setBrush(brush)
        for point in self.scale_points().values():
            painter.drawRect(QRectF(point.x() - size / 2, point.y() - size / 2, size, size))

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

    def multiplies_inside_only(self) -> bool:
        """Revu's Highlight on a shape with a border: only its inside — the
        fill and the hatch — multiplies onto the page; the border is drawn
        as it is (the user, 2026-10-18). A markup with no border (a
        highlight) or nothing inside (a line, the highlighter pen) still
        multiplies as a whole."""
        style = getattr(self, "style", None)
        if style is None or style.blend != "multiply" or getattr(self, "kind", "") == "highlighter":
            return False
        if self.still_theirs or self.stamp_svg or self._their_picture is not None:
            return False
        if not style.stroke or float(style.width or 0.0) <= 0 or not style.paints_inside():
            return False
        region = self.inside_region()
        return region is not None and not region.isEmpty()

    def inside_region(self) -> Optional[QPainterPath]:
        """What its fill covers, in item coordinates (its hatch's region)."""
        return self.hatch_region()

    def paint_inside(self, painter: QPainter) -> None:
        """Its fill and its hatch, and nothing else."""
        region = self.inside_region()
        if region is None or region.isEmpty():
            return
        if self.style.fill:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.fillPath(region, self.style.brush())
            painter.restore()
        paint_hatch(painter, region, self.style)

    def without_inside(self):
        """For the length of a ``with``: drawn with no fill and no hatch."""
        from contextlib import contextmanager

        @contextmanager
        def bare():
            style = self.style
            kept = (style.fill, style.hatch, style.hatch_tile)
            style.fill, style.hatch, style.hatch_tile = "", "", {}
            try:
                yield
            finally:
                style.fill, style.hatch, style.hatch_tile = kept
        return bare()

    def multiplies(self) -> bool:
        """Whether any of it multiplies onto the page (Highlight, the
        highlighter pen)."""
        style = getattr(self, "style", None)
        return style is not None and style.blend == "multiply"

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None) -> None:
        frame = self.parentItem()
        blend_pass = getattr(frame, "_blend_pass", "")
        if blend_pass:
            # a flattened markup going into a saved page, where a PDF writer
            # cannot multiply: the part drawn as it is, and the part that
            # multiplies on a layer of its own (io/pdfbase.py)
            painter.save()
            self._paint_blend_pass(painter, blend_pass)
            painter.restore()
            return
        if self.still_theirs:
            # its file draws it (_TheirLook): nothing of it is drawn here but
            # its handles — and this, for every markup of a marked-up set on
            # screen, every frame, was a tenth of one zoomed out
            self.paint_handles(painter)
            return
        painter.save()
        from ..ui.markuplayer import align_with_squares
        align_with_squares(painter, self)
        if not (self.split_theirs and (not getattr(frame, "print_mode", True)
                                       or self.split_from in getattr(frame, "file_drew_split", ()))):
            if self.multiplies_inside_only():
                # the inside multiplied onto the page, the border over it as it is
                painter.save()
                self.apply_blend(painter)
                self.paint_inside(painter)
                painter.restore()
                with self.without_inside():
                    self.paint_visible(painter)
            else:
                self.apply_blend(painter)
                self.paint_visible(painter)      # nothing while it is still theirs
        painter.restore()
        self.paint_handles(painter)

    def _paint_blend_pass(self, painter: QPainter, blend_pass: str) -> None:
        """"base": every markup that does not multiply; "multiply": what
        multiplies — a highlighted shape's inside, a highlighter's stroke;
        "over": a highlighted shape's border and the rest, over its inside."""
        if not self.multiplies():
            if blend_pass == "base":
                self.paint_visible(painter)
            return
        inside_only = self.multiplies_inside_only()
        if blend_pass == "multiply":
            if inside_only:
                self.paint_inside(painter)
            else:
                self.paint_visible(painter)
        elif blend_pass == "over" and inside_only:
            with self.without_inside():
                self.paint_visible(painter)

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
        # (but one the Markups List's filter dims is drawn alone, to be dimmed)
        wanted = bool(self.still_theirs and self.from_annotation
                      and (not getattr(self.parentItem(), "file_draws", False)
                           or self.filter_dimmed))
        if wanted and self._their_look is None:
            self._their_look = _TheirLook(self)
        if self._their_look is not None:
            self._their_look.prepareGeometryChange()
            self._their_look.setVisible(wanted)

    def show_whole_annotation(self, box) -> None:
        """Draw the ink annotation this stroke came from whole, by its file,
        in *box* (page points) — or stop, with None. Its first stroke does
        this while the Markups List's filter dims it, so it is dimmed with
        its real curves rather than the strokes' straight-line reading."""
        if box is None:
            if self._whole_look is not None:
                self._whole_look.setVisible(False)
            return
        if self._whole_look is None:
            self._whole_look = _TheirLook(self, number=self.split_from)
        self._whole_look.prepareGeometryChange()
        self._whole_look.box = QRectF(box)
        self._whole_look.setVisible(True)

    def paint_their_file(self, painter: QPainter, box=None, number=None) -> None:
        """On screen, a markup nobody has changed is drawn by its own file:
        its annotation alone, in squares the render processes draw, laid in
        its place among the other markups — so one taken over and moved does
        not suddenly cover those the file draws on top of it (Calcs.pdf,
        2026-10-01). The page itself is drawn without its markups.
        *number*: another annotation than this markup's own (an ink line's,
        drawn whole on its first stroke)."""
        frame = self.parentItem()
        page = getattr(frame, "page", None)
        number = number or self.from_annotation
        if (page is None or not number or getattr(frame, "print_mode", False)
                or not getattr(page, "pdf_key", None) or page.pdf_page_index is None
                or not getattr(page, "pdf_annotations", True)
                or number not in (page.markup_annotations or ())):
            return
        data = frame.document.asset(page.pdf_key)
        if not data:
            return
        pdftiles, _draw_on_the_pixel_grid, _painted_scale = _their_file_tools()
        to_page, ok = self.itemTransform(frame)
        back, inverted = to_page.inverted()
        ok = ok and inverted
        if not ok:
            return
        if box is None:
            box = self.mapRectToParent(self.boundingRect()).adjusted(-12, -12, 12, 12)
        whole = frame.page_rect()
        tiles = pdftiles.TILES.annotation_tiles(
            page.pdf_key, data, int(page.pdf_page_index), whole, _painted_scale(painter),
            box, number, box)
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
        # One picture for every markup showing the same asset: the same stamp
        # on each sheet of a set is one asset (pdfmarkups._the_file_draws_it),
        # and reading it once per sheet was two seconds of opening one.
        held = _PICTURES_READ.setdefault(document, {})
        known = held.get(self.their_picture_asset)
        if known is not None and known[0] is data:
            self._their_picture = known[1]
            return
        from PySide6.QtCore import QByteArray
        from PySide6.QtGui import QPixmap

        picture = QPixmap()
        if picture.loadFromData(QByteArray(data)) and not picture.isNull():
            self._their_picture = picture
            held[self.their_picture_asset] = (data, picture)

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
        elif change == QGraphicsItem.ItemSelectedChange:
            # picked out or let go: its handles' room comes or goes (not a
            # change to its drawing, so the page's squares keep it)
            self._may_leave_its_page()
            QGraphicsObject.prepareGeometryChange(self)
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            # Picking a markup out changes nothing about its drawing, only
            # whether its handles show; the page draws those over its squares.
            frame = self.parentItem()
            if self in getattr(getattr(frame, "layer", None), "members", ()):
                room = self.chrome_room()      # its handles, come or gone
                frame.update(self.mapRectToParent(self.bounds_without_chrome())
                             .adjusted(-room, -room, room, room))
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
        # An equation and a table turn about their corner, WebSMath's way
        # (they read upright while edited by turning back about it), and are
        # put back so: about their centre a table on a turned page came back
        # from a save somewhere else (2026-10-14).
        self.setTransformOriginPoint(QPointF(0, 0) if hasattr(self, "show_upright")
                                     else self.local_rect().center())
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
    if kind in ("open_reversed", "closed_reversed"):
        # the head turned round: its point a head's length back along the line
        back = tip - QPointF(math.cos(direction) * size, math.sin(direction) * size)
        return arrow_path(back, direction + math.pi, size,
                          "open" if kind == "open_reversed" else "arrow")
    if kind == "butt":
        offset = QPointF(math.cos(direction + math.pi / 2) * size * 0.45,
                         math.sin(direction + math.pi / 2) * size * 0.45)
        path.moveTo(tip - offset)
        path.lineTo(tip + offset)
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


def draw_head(painter: QPainter, tip: QPointF, direction: float, size: float,
              kind: str) -> None:
    """A line end of *kind*: filled with the brush in hand when it is a
    filled one (Closed, Round, Square, Diamond…), strokes only otherwise —
    an Open head left unfilled, as Bluebeam and every reader draw it."""
    if kind in ("none", ""):
        return
    if kind in FILLED_HEADS:
        painter.drawPath(arrow_path(tip, direction, size, kind))
        return
    brush = painter.brush()
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(arrow_path(tip, direction, size, kind))
    painter.setBrush(brush)


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


CLOUD_SIZE = 2.0        # a new cloud's Size (Bluebeam's Cloud tool)


def cloud_radius_for(size: float, line_width: float) -> float:
    """A cloud's scallop radius from its Size (the PDF's /BE intensity), as
    PDF readers draw a cloudy border: 4.75 × intensity + half the line width
    (Apache PDFBox, CloudyBorder)."""
    return 4.75 * max(float(size), 0.0) + 0.5 * max(float(line_width), 0.0)


def cloud_size_for(radius: float, line_width: float) -> float:
    return max((float(radius) - 0.5 * max(float(line_width), 0.0)) / 4.75, 0.05)


def cloud_path(polygon: QPolygonF, radius: float, closed: bool = True,
               inverted: bool = False) -> QPainterPath:
    """Convert a polyline into a Bluebeam-style revision cloud; *inverted*
    turns the scallops the other way (Bluebeam's Invert)."""
    key = (tuple((point.x(), point.y()) for point in polygon), radius, closed, inverted)
    made = _CLOUDS.get(key)
    if made is None:
        made = _cloud_path(polygon, radius, closed, inverted)
        if len(_CLOUDS) > 2048:
            _CLOUDS.clear()
        _CLOUDS[key] = made
    return QPainterPath(made)


#: Clouds and pens already worked out: the same cloud is drawn again on every
#: repaint and into every square it crosses.
_CLOUDS: dict = {}
_PENS: dict = {}


def _cloud_path(polygon: QPolygonF, radius: float, closed: bool = True,
                inverted: bool = False) -> QPainterPath:
    """A revision cloud round *polygon*: scallops of *radius*, centred on the
    outline, one at each corner and the rest spaced evenly along each side,
    as Revu draws them. Neighbouring scallops meet in a cusp where their
    circles cross outside the outline, at the same spacing and depth as a PDF
    reader's cloudy border (Apache PDFBox's CloudyBorder: centres 2·cos 34°
    × radius apart). The curls bulge outward; *inverted* (Bluebeam's Invert)
    turns them inward.

    Each scallop is drawn from the cusp it shares with the one before to the
    cusp it shares with the one after, and the last ends where the first
    began. The PDFBox shape this replaced eased its leftover length into the
    first scallops of each side and began each corner with a short curl
    drawn backwards: where the path closed, at the south-east corner of a
    dragged cloud, that showed as a hook, and the eased scallops overlapped
    their corner (QA, 2026-10-15).
    Worked in y-up coordinates, as the PDF's own, and turned back."""
    points = [(p.x(), -p.y()) for p in polygon]
    # no zero-length sides, and not closed (the first point is not repeated)
    clean = []
    for pt in points:
        if not clean or math.hypot(pt[0] - clean[-1][0], pt[1] - clean[-1][1]) > 1e-9:
            clean.append(pt)
    if len(clean) >= 2 and math.hypot(clean[0][0] - clean[-1][0],
                                      clean[0][1] - clean[-1][1]) <= 1e-9:
        clean.pop()
    path = QPainterPath()
    if len(clean) < 3:
        return path
    # anticlockwise (y up), so outward is to the right of the way round —
    # or the other way round, which turns the scallops inward
    area = sum(clean[i][0] * clean[(i + 1) % len(clean)][1]
               - clean[i][1] * clean[(i + 1) % len(clean)][0] for i in range(len(clean)))
    if (area < 0) != inverted:
        clean.reverse()
    radius = max(float(radius), 0.5)
    pitch = 2 * math.cos(math.radians(34)) * radius

    # the scallops' centres, each with the way round at that point
    centres = []
    count = len(clean)
    for i in range(count):
        (x0, y0), (x1, y1) = clean[i], clean[(i + 1) % count]
        length = math.hypot(x1 - x0, y1 - y0)
        if length <= 1e-9:
            continue
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        steps = max(1, math.ceil(length / pitch - 1e-9))
        for step in range(steps):
            t = length * step / steps
            centres.append((x0 + ux * t, y0 + uy * t, ux, uy))
    # sides much shorter than a scallop: one scallop, not a pile of them
    kept = []
    for centre in centres:
        if kept and math.hypot(centre[0] - kept[-1][0], centre[1] - kept[-1][1]) < 0.35 * radius:
            continue
        kept.append(centre)
    while (len(kept) > 3 and math.hypot(kept[0][0] - kept[-1][0],
                                        kept[0][1] - kept[-1][1]) < 0.35 * radius):
        kept.pop()
    centres = kept
    if len(centres) < 3:
        return path
    # circles that would not cross (a cloud smaller than its scallops) are
    # made just big enough to
    widest = max(math.hypot(centres[(i + 1) % len(centres)][0] - centres[i][0],
                            centres[(i + 1) % len(centres)][1] - centres[i][1])
                 for i in range(len(centres)))
    radius = max(radius, widest / (2 * math.cos(math.radians(34))))

    def cusp(a, b):
        """Where the circles round centres *a* and *b* cross on the outside
        (to the right of the way from a to b)."""
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        h = math.sqrt(max(radius * radius - d * d / 4, 0.0))
        return mx + h * dy / d, my - h * dx / d

    def out(x, y):
        return QPointF(x, -y)

    def segment(cx, cy, start, end):
        half = (end - start) / 2.0
        ca, sa, cb, sb = math.cos(start), math.sin(start), math.cos(end), math.sin(end)
        bcp = 4.0 / 3.0 * (1 - math.cos(half)) / math.sin(half)
        path.cubicTo(out(cx + radius * (ca - bcp * sa), cy + radius * (sa + bcp * ca)),
                     out(cx + radius * (cb + bcp * sb), cy + radius * (sb - bcp * cb)),
                     out(cx + radius * cb, cy + radius * sb))

    total = len(centres)
    cusps = [cusp(centres[i - 1], centres[i]) for i in range(total)]
    path.moveTo(out(*cusps[0]))
    for i, (cx, cy, ux, uy) in enumerate(centres):
        (sx, sy), (ex, ey) = cusps[i], cusps[(i + 1) % total]
        start = math.atan2(sy - cy, sx - cx)
        sweep = (math.atan2(ey - cy, ex - cx) - start) % (2 * math.pi)
        # the arc round the outside: its middle to the right of the way round
        middle = start + sweep / 2
        if ux * math.sin(middle) - uy * math.cos(middle) > 0:
            sweep -= 2 * math.pi
        pieces = max(1, math.ceil(abs(sweep) / (math.pi / 2) - 1e-9))
        for piece in range(pieces):
            segment(cx, cy, start + sweep * piece / pieces,
                    start + sweep * (piece + 1) / pieces)
    path.closeSubpath()
    return path


_THEIR_FILE_TOOLS = None


def _their_file_tools():
    """The tile cache and the scene's drawing on the pixel grid, imported
    once (they import this module): an import in a paint goes through
    PySide's import hook, a dozen microseconds for every markup on screen
    every frame."""
    global _THEIR_FILE_TOOLS
    if _THEIR_FILE_TOOLS is None:
        from ..io import pdftiles
        from ..ui.scene import _draw_on_the_pixel_grid, _painted_scale
        _THEIR_FILE_TOOLS = (pdftiles, _draw_on_the_pixel_grid, _painted_scale)
    return _THEIR_FILE_TOOLS


class _TheirLook(QGraphicsItem):
    """The file's own drawing of a markup nobody has changed, in the box the
    file gives it (/Rect) — not the box this application would measure:
    Bluebeam puts a dimension's words out at the end of a leader, and drawn
    inside the markup's own box "1m" was cut away (the user, 2026-10-01).
    It belongs to its markup, so it is stacked with it among the others; it
    takes no clicks, and goes the moment the markup is changed."""

    MARKUP_LOOK = True
    _baked_rect = None
    #: another annotation than its markup's own, in a box of its own (an ink
    #: line drawn whole on its first stroke: MarkupItem.show_whole_annotation)
    number = None
    box = None

    def __init__(self, markup, number=None):
        super().__init__(markup)
        self.number = number
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setAcceptHoverEvents(False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsFocusable, False)

    def _page_box(self) -> QRectF:
        markup = self.parentItem()
        if self.box is not None:
            return QRectF(self.box)
        if markup.their_box:
            return QRectF(*markup.their_box)
        return markup.mapRectToParent(markup.boundingRect()).adjusted(-12, -12, 12, 12)

    _bounds = None
    _bounds_for = None

    def boundingRect(self) -> QRectF:
        if self._baked_rect is not None:
            return self._baked_rect
        markup = self.parentItem()
        if markup is None or markup.parentItem() is None:
            return QRectF()
        if self.box is not None:
            return markup.mapRectFromParent(self.box).adjusted(-2, -2, 2, 2)
        if not markup.their_box:
            return markup.mapRectFromParent(self._page_box()).adjusted(-2, -2, 2, 2)
        # the same while its markup stays where it is and its box is the same
        position = markup.pos()
        key = (position.x(), position.y(), markup.their_box, markup.rotation(), markup.scale())
        if self._bounds is not None and self._bounds_for == key and markup.transform().isIdentity():
            return self._bounds
        self._bounds = markup.mapRectFromParent(self._page_box()).adjusted(-2, -2, 2, 2)
        self._bounds_for = key
        return self._bounds

    def shape(self):
        from PySide6.QtGui import QPainterPath
        return QPainterPath()                      # nothing to click on

    def paint(self, painter: QPainter, option, widget=None) -> None:
        markup = self.parentItem()
        if markup is None:
            return
        if self.number:
            if markup.split_theirs:          # every stroke untouched still
                painter.save()
                markup.paint_their_file(painter, self._page_box().adjusted(-1, -1, 1, 1),
                                        self.number)
                painter.restore()
            return
        if not markup.still_theirs:
            return
        engine = painter.paintEngine()
        if (markup.style.blend == "multiply" and engine is not None
                and engine.type() == engine.Type.OpenGL2):
            return                     # the page draws it (markups_drawn_alone)
        painter.save()
        markup.apply_blend(painter)
        markup.paint_their_file(painter, self._page_box().adjusted(-1, -1, 1, 1))
        painter.restore()
