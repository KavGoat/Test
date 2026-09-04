"""Text-bearing markups: text boxes, callouts, sticky notes and stamps."""
from __future__ import annotations

import math
import re
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QAbstractTextDocumentLayout, QBrush, QColor, QPainter,
                           QPainterPath, QPainterPathStroker, QPalette, QPen,
                           QPolygonF,
                           QSyntaxHighlighter, QTextCharFormat, QTextCursor,
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

    # What ends a run of subscript or superscript: anything that is not part
    # of the same token. A space, an operator, a bracket — the moment the
    # writing moves on, so does the level.
    ENDS_A_RUN = set(" \t,;:()[]{}+-*/=<>")

    def keyPressEvent(self, event) -> None:
        """``_`` drops what follows; ``^`` lifts it — as they do in maths.

        Writing "150x50 SG8 at 400 c/c" needs no help, but "A_g", "m^2" and
        "f'_c" are on every page of a calculation, and reaching for a menu to
        set one character is not writing. So the two characters an engineer
        already types for it do it: what follows a ``_`` is set as a
        subscript and what follows a ``^`` as a superscript, until a space or
        an operator says the word has finished.
        """
        text = event.text()
        if text == "\\" and not (event.modifiers() & Qt.ControlModifier):
            # A field: what goes between the two marks is worked out from the
            # document and printed in its place. The caret lands between them,
            # so what follows is typed straight into the field.
            cursor = self.textCursor()
            cursor.insertText("\\\\")
            cursor.movePosition(QTextCursor.Left)
            self.setTextCursor(cursor)
            event.accept()
            return
        if text in ("_", "^") and not (event.modifiers() & Qt.ControlModifier):
            self.set_script("sub" if text == "_" else "super")
            event.accept()
            return
        if text and (text in self.ENDS_A_RUN or event.key() in (Qt.Key_Return,
                                                                Qt.Key_Enter)):
            self.set_script("")
        super().keyPressEvent(event)

    def set_script(self, level: str) -> None:
        """Put the caret into subscript, superscript or back on the line."""
        cursor = self.textCursor()
        fmt = QTextCharFormat()
        fmt.setVerticalAlignment({
            "sub": QTextCharFormat.AlignSubScript,
            "super": QTextCharFormat.AlignSuperScript,
        }.get(level, QTextCharFormat.AlignNormal))
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            # A graphics text item has no "current char format" of its own,
            # so the level is put on the cursor and the cursor put back: the
            # next character typed comes out wearing it.
            cursor.mergeBlockCharFormat(fmt)
            cursor.setCharFormat(_merged(cursor.charFormat(), fmt))
        self.setTextCursor(cursor)


def _as_text(value, digits: int = 4) -> str:
    """A value as it would be written in a sentence."""
    from ..core.units import Quantity, format_number, format_quantity

    if value is None:
        return "—"
    if isinstance(value, Quantity):
        return format_quantity(value, digits, "auto")
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return format_number(value, digits)
    return str(value)


def _crosses(rect: QRectF, a: QPointF, b: QPointF) -> bool:
    """Whether the line from *a* to *b* runs across *rect*.

    Used to keep a leader off its own words: a hinge put on the far side of
    the box would send the line back over the writing to reach the arrow
    head, and that is not somewhere the hinge is allowed to be.

    The box is shrunk a whisker first, so a line that only grazes an edge —
    which is what every leader does where it leaves the box — does not count
    as crossing it.
    """
    box = QRectF(rect).normalized().adjusted(0.75, 0.75, -0.75, -0.75)
    if box.width() <= 0 or box.height() <= 0:
        return False
    if box.contains(a) or box.contains(b):
        return True
    corners = [box.topLeft(), box.topRight(), box.bottomRight(),
               box.bottomLeft()]
    for index in range(4):
        if _segments_cross(a, b, corners[index], corners[(index + 1) % 4]):
            return True
    return False


def _distance_to_segment(a: QPointF, b: QPointF, p: QPointF) -> float:
    """How far *p* is from the line between *a* and *b*."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    if dx == 0 and dy == 0:
        return math.hypot(p.x() - a.x(), p.y() - a.y())
    along = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy)
                         / (dx * dx + dy * dy)))
    return math.hypot(p.x() - (a.x() + along * dx), p.y() - (a.y() + along * dy))


def _segments_cross(a: QPointF, b: QPointF, c: QPointF, d: QPointF) -> bool:
    """Whether two line segments meet anywhere."""
    def side(p: QPointF, q: QPointF, r: QPointF) -> float:
        return ((q.x() - p.x()) * (r.y() - p.y())
                - (q.y() - p.y()) * (r.x() - p.x()))

    one, two = side(a, b, c), side(a, b, d)
    three, four = side(c, d, a), side(c, d, b)
    return ((one > 0) != (two > 0)) and ((three > 0) != (four > 0))


class _Leader:
    """One arrow: what it points at, which side it leaves by, how far out.

    The hinge is not a point that gets stored. It is worked out, every time,
    from the side and the reach: the middle of that side, straight out at
    right angles, *reach* away. That is what makes it perpendicular to the
    side however the box or the arrow head is moved, and it is why moving
    either of them puts the hinge somewhere sensible instead of leaving it
    where it was last dropped.

    *side* is normally empty, meaning "whichever side faces what this points
    at" — which is what a leader does when nobody has touched it. Dragging
    the hinge round to another side of the box fills it in; moving the arrow
    head or the box empties it again, and the hinge goes back to working
    itself out.

    A leader points at something in one of two ways. An *arrow* leader ends in
    an arrow head at the place it is about. A *cloud* leader ends at a region
    drawn round with a cloud, and has no head — the cloud is what does the
    pointing, and the line only says which note belongs to which cloud. They
    are the same leader otherwise: the same hinge, the same rule about not
    crossing the box, the same several-at-once, and one call-out can carry
    both kinds at the same time.
    """

    __slots__ = ("tip", "side", "reach", "kind", "cloud")

    SIDES = ("left", "right", "top", "bottom")
    KINDS = ("arrow", "cloud")

    def __init__(self, tip: QPointF, side: str = "", reach: float = 24.0,
                 kind: str = "arrow", cloud=None):
        self.tip = QPointF(tip)
        self.side = side if side in self.SIDES else ""
        self.reach = max(float(reach), 6.0)
        self.kind = kind if kind in self.KINDS else "arrow"
        # The region a cloud leader is about, in the item's own coordinates.
        self.cloud: list[QPointF] = [QPointF(p) for p in (cloud or [])]

    # -- the clouded region ------------------------------------------------
    def clouds(self) -> bool:
        return self.kind == "cloud" and len(self.cloud) >= 3

    def cloud_box(self) -> QRectF:
        """The rectangle the clouded region sits in."""
        if not self.cloud:
            return QRectF()
        xs = [p.x() for p in self.cloud]
        ys = [p.y() for p in self.cloud]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def join_nearest(self, to: QPointF) -> QPointF:
        """Where the line meets the cloud: the corner or edge middle nearest *to*.

        So the line takes the shortest way across and lands somewhere that
        reads as a deliberate join rather than as a line that stops near it.
        """
        if not self.cloud:
            return QPointF(self.tip)
        candidates = list(self.cloud)
        for index, point in enumerate(self.cloud):
            following = self.cloud[(index + 1) % len(self.cloud)]
            candidates.append(QPointF((point.x() + following.x()) / 2,
                                      (point.y() + following.y()) / 2))
        return min(candidates, key=lambda point:
                   (point.x() - to.x()) ** 2 + (point.y() - to.y()) ** 2)

    def move_by(self, dx: float, dy: float) -> None:
        """Shift the whole leader — its tip and, for a cloud, its region."""
        self.tip = QPointF(self.tip.x() + dx, self.tip.y() + dy)
        self.cloud = [QPointF(p.x() + dx, p.y() + dy) for p in self.cloud]

    def to_dict(self) -> dict:
        data = {"tip": [self.tip.x(), self.tip.y()], "reach": self.reach}
        if self.side:
            data["side"] = self.side
        if self.kind != "arrow":
            data["kind"] = self.kind
        if self.cloud:
            data["cloud"] = [[p.x(), p.y()] for p in self.cloud]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "_Leader":
        tip = data.get("tip") or [0.0, 0.0]
        cloud = [QPointF(float(p[0]), float(p[1]))
                 for p in (data.get("cloud") or [])]
        return cls(QPointF(float(tip[0]), float(tip[1])),
                   str(data.get("side") or ""),
                   float(data.get("reach", 24.0)),
                   str(data.get("kind") or "arrow"), cloud)


def _merged(base: QTextCharFormat, extra: QTextCharFormat) -> QTextCharFormat:
    """*base* with *extra* laid over it — the font and colour are kept."""
    out = QTextCharFormat(base)
    out.merge(extra)
    return out


class _SpellHighlighter(QSyntaxHighlighter):
    """Red squiggles under the words the dictionary does not know."""

    def highlightBlock(self, text: str) -> None:
        from ..core.spelling import shared

        checker = shared()
        if not checker.ready():
            return
        style = QTextCharFormat()
        style.setUnderlineColor(QColor("#e03131"))
        style.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
        for start, length, _word in checker.mistakes(text):
            self.setFormat(start, length, style)


class _TextBase(MarkupItem):
    """Shared rich-text behaviour: document, layout, in-place editing."""

    HAS_TEXT = True
    ELBOW_REACH = 24.0          # how far the hinge stands off the box by default
    LEAST_REACH = 8.0           # and the closest it may ever be dragged in

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
        self._speller = None
        self._editing = False
        # Any text box can have a leader; a call-out is simply one that starts
        # with it shown. It is off here so a plain text box has no arrow until
        # one is asked for.
        # Any text box can have leaders; a call-out is simply one that starts
        # with one. As many as the note needs: one comment about three bolts
        # wants three arrows, not three copies of the comment.
        self.leaders: list[_Leader] = []
        # What was typed, fields and all. The document holds what is *shown*,
        # which is the same thing once the fields have been worked out.
        self.written = text
        self.digits = 4
        self.doc.contentsChanged.connect(self._on_contents_changed)

    # -- fields ------------------------------------------------------------
    #
    # A paragraph on a calculation sheet nearly always wants to quote a number
    # that is worked out somewhere else: "the design moment of \\M_n\\ governs".
    # Typing the number in by hand means it is wrong the moment anything above
    # it changes. A field between two backslashes is worked out from the
    # document every time the sheet is recalculated, so it cannot go stale.
    #
    # A field holding a bare name that the document defines prints as
    # "name = value unit", because that is how it would be written by hand.
    # Anything else is worked out and its answer printed on its own.
    FIELD = re.compile(r"\\([^\\\n]+)\\")

    def has_fields(self) -> bool:
        return bool(self.FIELD.search(self.written))

    def resolve_fields(self, workspace) -> str:
        """*written* with every field replaced by what it comes to."""
        from ..core import engine
        from ..core.units import format_quantity

        def answer(match) -> str:
            source = match.group(1).strip()
            if not source:
                return match.group(0)
            try:
                if workspace is not None and workspace.has(source):
                    value = workspace.get(source)
                    shown = _as_text(value, self.digits)
                    return f"{source} = {shown}"
                if workspace is None:
                    return match.group(0)
                value = workspace.evaluate(source)
            except Exception:                # noqa: BLE001 — any bad field
                return f"[{source}?]"
            return _as_text(value, self.digits)

        return self.FIELD.sub(answer, self.written)

    def refresh(self, workspace=None, page=None) -> None:
        """Work every field out again, so the prose keeps up with the sheet."""
        if self._editing or not self.has_fields():
            return
        shown = self.resolve_fields(workspace)
        if shown != self.doc.toPlainText():
            self.doc.setPlainText(shown)
            self.apply_style()

    # -- content -----------------------------------------------------------
    def text(self) -> str:
        return self.doc.toPlainText()

    def set_text(self, text: str) -> None:
        self.written = text
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
        """Grow to hold what has been typed — and never shrink on its own.

        A box that closed up every time a word was deleted would jump about
        under the caret. Growing is help; shrinking is interference. Alt+Z
        (:meth:`size_to_text`) is how a box is brought back in when its size
        really is wrong.
        """
        self.doc.setTextWidth(max(self.text_rect().width(), 8.0))
        needed = self.doc.size().height() + 2 * self.style.padding
        if needed > self._rect.height():
            self._rect.setHeight(needed)

    def size_to_text(self) -> None:
        """Shrink-wrap the box around the words in it."""
        pad = self.style.padding
        self.prepareGeometryChange()
        self.doc.setTextWidth(max(self.text_rect().width(), 8.0))
        ideal = self.doc.idealWidth() + 2 * pad
        rect = QRectF(self._rect.normalized())
        rect.setWidth(max(min(rect.width(), max(ideal, 24.0)), 24.0))
        self._rect = rect
        self.doc.setTextWidth(max(self.text_rect().width(), 8.0))
        height = self.doc.size().height() + 2 * pad
        self._rect.setHeight(max(height, 2 * pad + 8.0))
        self.apply_style()
        self.touch()
        self.update()

    # -- geometry ----------------------------------------------------------
    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)
        self.apply_style()
        self._sync_editor()

    # -- the leaders -------------------------------------------------------
    #
    # A leader is a text box's arrow: it leaves one side of the box, turns a
    # corner at its elbow, and runs to the tip. A call-out is a text box drawn
    # with one; a plain text box or a typewriter can be given one afterwards,
    # and any of them can have as many as the note needs — one comment about
    # three bolts wants three arrows, not three copies of the comment.
    #
    # Which side a leader leaves by is worked out, not chosen: it is the side
    # its elbow faces. Drag the elbow round to the top of the box and the
    # leader starts leaving from the top, which is the only behaviour that
    # does not need explaining.

    @property
    def leader_shown(self) -> bool:
        return bool(self.leaders)

    @leader_shown.setter
    def leader_shown(self, wanted: bool) -> None:
        if wanted and not self.leaders:
            self.add_leader()
        elif not wanted:
            self.leaders = []

    # The first leader, for everything that only ever deals with one.
    @property
    def tip(self) -> QPointF:
        return self.leaders[0].tip if self.leaders else QPointF()

    @tip.setter
    def tip(self, point) -> None:
        if not self.leaders:
            self.leaders = [_Leader(QPointF(point))]
        else:
            self.leaders[0].tip = QPointF(point)

    @property
    def elbow_reach(self) -> float:
        return self.leaders[0].reach if self.leaders else self.ELBOW_REACH

    @elbow_reach.setter
    def elbow_reach(self, reach: float) -> None:
        for leader in self.leaders:
            leader.reach = float(reach)

    @property
    def leader(self) -> list:
        """The first leader as points, tip first — for older callers."""
        if not self.leaders:
            return []
        first = self.leaders[0]
        return [QPointF(first.tip), self.elbow_of(first), self.side_point_of(first)]

    @leader.setter
    def leader(self, points) -> None:
        """Older documents kept the leader as a list of points."""
        points = [QPointF(p) for p in points]
        if points:
            self.tip = QPointF(points[0])

    # -- adding and taking away --------------------------------------------
    def add_leader(self, tip: Optional[QPointF] = None) -> "_Leader":
        """Give the box another leader. Says which one it made."""
        self.prepareGeometryChange()
        if tip is None:
            tip = self._room_for_another_leader()
        leader = _Leader(QPointF(tip), "", self.ELBOW_REACH)
        self.leaders.append(leader)
        if self.style.arrow_end == "none":
            self.style.arrow_end = "arrow"
        self.geometryChanged.emit()
        return leader

    def remove_leader(self, index: Optional[int] = None) -> None:
        """Take one leader away — the last, or the one asked for."""
        if not self.leaders:
            return
        self.prepareGeometryChange()
        if index is None:
            self.leaders = []
        elif 0 <= index < len(self.leaders):
            del self.leaders[index]
        self.geometryChanged.emit()

    def _room_for_another_leader(self) -> QPointF:
        """Where a new arrow starts out: clear of the box and of the others.

        Fanned out below and to the left, a step further along each time, so
        two arrows added one after the other do not land on top of each other
        and have to be pulled apart before either can be aimed.
        """
        box = self._rect.normalized()
        step = len(self.leaders)
        return QPointF(box.left() - 60 - step * 18,
                       box.bottom() + 50 + step * 26)

    # -- where each one leaves the box -------------------------------------
    #
    # The whole shape of a leader comes out of two numbers: which side it
    # leaves by, and how far out it turns its corner. Everything else follows.
    # It leaves the middle of that side square on, turns once, and runs to
    # what it points at — which is the shape a call-out has on every drawing
    # anybody has ever read.

    def facing_side(self, leader: "_Leader") -> str:
        """The side that faces what this leader points at.

        Worked out from the arrow head against the corners of the box, so a
        tip out beyond a corner picks the side it is most beyond rather than
        the one it is nearest the middle of.
        """
        rect = self._rect.normalized()
        centre = rect.center()
        half_width = max(rect.width() / 2, 1.0)
        half_height = max(rect.height() / 2, 1.0)
        tip = self.tip_of(leader)
        across = (tip.x() - centre.x()) / half_width
        down = (tip.y() - centre.y()) / half_height
        if abs(across) >= abs(down):
            return "left" if across < 0 else "right"
        return "top" if down < 0 else "bottom"

    def side_of(self, leader: "_Leader") -> str:
        """Which side this leader actually leaves by."""
        if leader.side and self.side_is_usable(leader, leader.side):
            return leader.side
        return self.facing_side(leader)

    def side_is_usable(self, leader: "_Leader", side: str) -> bool:
        """Whether a leader could leave by *side* without crossing the words.

        A hinge put on the far side of the box sends the line back across
        the writing to reach the arrow head, which is unreadable — so those
        sides are simply not offered. Anything else is allowed, including the
        two sides at right angles to the obvious one, which is how a leader
        gets tucked out of the way of another markup.
        """
        rect = self._rect.normalized()
        hinge = self.hinge_on(side, leader.reach)
        return not _crosses(rect, hinge, self.tip_of(leader))

    def side_point_of(self, leader: "_Leader") -> QPointF:
        """The middle of the side this leader leaves by."""
        return self.middle_of(self.side_of(leader))

    def middle_of(self, side: str) -> QPointF:
        rect = self._rect.normalized()
        return {
            "left": QPointF(rect.left(), rect.center().y()),
            "right": QPointF(rect.right(), rect.center().y()),
            "top": QPointF(rect.center().x(), rect.top()),
            "bottom": QPointF(rect.center().x(), rect.bottom()),
        }.get(side, rect.center())

    @staticmethod
    def normal_of(side: str) -> QPointF:
        """Straight out of that side, away from the box."""
        return {"left": QPointF(-1, 0), "right": QPointF(1, 0),
                "top": QPointF(0, -1),
                "bottom": QPointF(0, 1)}.get(side, QPointF(-1, 0))

    def side_normal_of(self, leader: "_Leader") -> QPointF:
        return self.normal_of(self.side_of(leader))

    def hinge_on(self, side: str, reach: float) -> QPointF:
        """Where the corner would be if it left by *side*, *reach* out."""
        start = self.middle_of(side)
        normal = self.normal_of(side)
        out = max(float(reach), self.LEAST_REACH)
        return QPointF(start.x() + normal.x() * out, start.y() + normal.y() * out)

    def elbow_of(self, leader: "_Leader") -> QPointF:
        """Where this leader turns its corner: square out of its own side."""
        return self.hinge_on(self.side_of(leader), leader.reach)

    def set_elbow_of(self, leader: "_Leader", local_pos: QPointF) -> None:
        """Put the hinge where the pointer asks, as near as it is allowed.

        Which side is taken from where the pointer is; how far out is how far
        the pointer is from that side, along its perpendicular. So dragging
        it round to the top makes the leader leave from the top, and dragging
        it away from the box pushes the corner further out — but it never
        comes off the perpendicular, and it is never put somewhere that would
        send the line back across the words.
        """
        self.prepareGeometryChange()
        wanted = self._nearest_side(local_pos)
        out = self._reach_towards(wanted, local_pos)
        trial = _Leader(leader.tip, wanted, out, leader.kind, leader.cloud)
        if not self.side_is_usable(trial, wanted):
            # That side would drag the line back over the writing. Nothing
            # changes: the pointer is off beside a side the leader cannot
            # use, so how far out it is there says nothing about how far out
            # the hinge should stand on the side it is actually on.
            return
        leader.side = "" if wanted == self.facing_side(leader) else wanted
        leader.reach = out
        self.touch()
        self.geometryChanged.emit()

    def _nearest_side(self, local_pos: QPointF) -> str:
        """Which side of the box the pointer is off, by its own perpendicular."""
        rect = self._rect.normalized()
        centre = rect.center()
        half_width = max(rect.width() / 2, 1.0)
        half_height = max(rect.height() / 2, 1.0)
        across = (local_pos.x() - centre.x()) / half_width
        down = (local_pos.y() - centre.y()) / half_height
        if abs(across) >= abs(down):
            return "left" if across < 0 else "right"
        return "top" if down < 0 else "bottom"

    def _reach_towards(self, side: str, local_pos: QPointF) -> float:
        """How far out along that side's perpendicular the pointer is."""
        start = self.middle_of(side)
        normal = self.normal_of(side)
        along = ((local_pos.x() - start.x()) * normal.x()
                 + (local_pos.y() - start.y()) * normal.y())
        return max(along, self.LEAST_REACH)

    def clouds_a_region(self) -> bool:
        """A plain text box never clouds anything; a call-out may."""
        return False

    def leader_near(self, local_pos: QPointF,
                    reach: float = 14.0) -> Optional[int]:
        """Which leader the pointer is on, if it is on one.

        Anywhere along it counts — the arrow head, the hinge, or the line
        between them — because "this one" means the one being pointed at, not
        the one whose handle was found first.
        """
        best, nearest = None, reach
        for index, leader in enumerate(self.leaders):
            start = self.side_point_of(leader)
            hinge = self.elbow_of(leader)
            for a, b in ((start, hinge), (hinge, self.tip_of(leader))):
                gap = _distance_to_segment(a, b, local_pos)
                if gap < nearest:
                    best, nearest = index, gap
        return best

    def leader_moved(self) -> None:
        """The arrow head or the box moved: work the hinges out again.

        A hinge that was dragged to a particular side made sense against the
        arrow head as it then was. Moved somewhere else, that side may now
        be behind the box, so the choice is given up and the leader goes back
        to leaving by whichever side faces what it points at.
        """
        for leader in self.leaders:
            leader.side = ""

    # -- the one-leader spellings, kept for everything that uses them ------
    def side(self) -> str:
        return self.side_of(self.leaders[0]) if self.leaders else "left"

    def side_point(self) -> QPointF:
        return (self.side_point_of(self.leaders[0]) if self.leaders
                else self._rect.normalized().center())

    def side_normal(self) -> QPointF:
        return (self.side_normal_of(self.leaders[0]) if self.leaders
                else QPointF(-1, 0))

    def elbow(self) -> QPointF:
        return self.elbow_of(self.leaders[0]) if self.leaders else QPointF()

    def set_elbow_from(self, local_pos: QPointF) -> None:
        if self.leaders:
            self.set_elbow_of(self.leaders[0], local_pos)

    # -- handles and moving ------------------------------------------------
    def leader_handles(self) -> set[str]:
        """The handles that belong to the arrows rather than to the box."""
        keys = set()
        for index in range(len(self.leaders)):
            keys.add(f"l{index}")
            keys.add(f"e{index}")
        return keys

    def move_keeping_leader(self, position: QPointF) -> None:
        """Move the box and leave the arrows pointing where they pointed."""
        delta = position - self.pos()
        if self.leaders and not delta.isNull():
            self.prepareGeometryChange()
            for leader in self.leaders:
                # The whole leader stays where it was — its head, and the
                # region a cloud leader is drawn round.
                leader.move_by(-delta.x(), -delta.y())
            # The box has moved, so a side that was chosen by hand may now be
            # the wrong one. The hinges work themselves out again.
            self.leader_moved()
        self.setPos(position)

    # -- painting ----------------------------------------------------------
    def paint_leader(self, painter: QPainter) -> None:
        """Draw every arrow this box has."""
        if not self.leaders:
            return
        # A typewriter has no border, and a text box may have had its turned
        # off — but a leader with no line is just a floating arrow head, so it
        # borrows the text colour rather than disappearing.
        pen = self.style.pen()
        if not self.style.stroke or self.style.width <= 0:
            pen = QPen(self.style.text_qcolor())
            pen.setWidthF(1.0)
        for leader in self.leaders:
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            elbow = self.elbow_of(leader)
            tip = self.tip_of(leader)
            path = QPainterPath(tip)
            path.lineTo(elbow)
            path.lineTo(self.side_point_of(leader))
            painter.drawPath(path)
            if leader.clouds():
                # The cloud is what points at the thing, so there is no head
                # on the line: it only says which note goes with which cloud.
                from .base import cloud_path
                painter.drawPath(cloud_path(QPolygonF(list(leader.cloud)),
                                            self.cloud_radius_of(leader)))
                continue
            if self.style.arrow_end != "none":
                angle = math.atan2(tip.y() - elbow.y(), tip.x() - elbow.x())
                colour = QColor(pen.color())
                colour.setAlphaF(self.style.opacity)
                painter.setBrush(QBrush(colour))
                painter.drawPath(arrow_path(tip, angle,
                                            max(self.style.width * 4.5, 8.0),
                                            self.style.arrow_end))

    def cloud_radius_of(self, _leader) -> float:
        """How big the puffs on a cloud leader are."""
        return getattr(self, "cloud_radius", 9.0)

    def tip_of(self, leader) -> QPointF:
        """Where the leader's line ends.

        An arrow leader ends at the place it points to. A cloud leader ends
        where its line meets the cloud — the nearest corner or edge middle to
        the note — so the join moves with the box and the region rather than
        being remembered from wherever it was first drawn.
        """
        if leader.clouds():
            return leader.join_nearest(self._rect.normalized().center())
        return QPointF(leader.tip)

    def leader_points(self) -> list:
        """Every point every leader passes through, for measuring the item."""
        points = []
        for leader in self.leaders:
            points += [self.tip_of(leader), self.elbow_of(leader),
                       self.side_point_of(leader)]
            points += [QPointF(p) for p in leader.cloud]
        return points

    # -- geometry, once the leader is taken into account -------------------
    def boundingRect(self) -> QRectF:
        rect = QRectF(self._rect)
        for point in self.leader_points():
            rect = rect.united(QRectF(point.x() - 1, point.y() - 1, 2, 2))
        margin = self.style.width + HANDLE_SIZE + 12
        return rect.normalized().adjusted(-margin, -margin, margin, margin)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._rect.normalized().adjusted(-3, -3, 3, 3))
        if self.leaders:
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.style.width, 6.0) + 4)
            for leader in self.leaders:
                line = QPainterPath(self.tip_of(leader))
                line.lineTo(self.elbow_of(leader))
                line.lineTo(self.side_point_of(leader))
                path.addPath(stroker.createStroke(line))
                if leader.clouds():
                    path.addPolygon(QPolygonF(list(leader.cloud)))
        return path

    def handle_points(self) -> dict[str, QPointF]:
        handles = super().handle_points()
        if not self.leaders:
            return handles
        handles.pop("rot", None)
        for index, leader in enumerate(self.leaders):
            # A cloud leader has no arrow head to take hold of, so its handle
            # sits on the cloud: dragging it carries the whole region.
            handles[f"l{index}"] = (leader.cloud_box().center() if leader.clouds()
                                    else QPointF(leader.tip))
            handles[f"e{index}"] = self.elbow_of(leader)
        return handles

    def leader_at(self, key: str):
        """The leader a handle key belongs to, and what the key moves."""
        if key == "elbow" and self.leaders:
            return self.leaders[0], "elbow"
        if len(key) > 1 and key[0] in "le" and key[1:].isdigit():
            index = int(key[1:])
            if 0 <= index < len(self.leaders):
                return self.leaders[index], ("tip" if key[0] == "l" else "elbow")
        return None, ""

    def move_handle(self, key: str, local_pos: QPointF, keep_ratio: bool = False) -> None:
        leader, part = self.leader_at(key)
        if leader is not None:
            if part == "tip":
                self.prepareGeometryChange()
                if leader.clouds():
                    # The whole clouded region travels, keeping its shape.
                    was = leader.cloud_box().center()
                    leader.move_by(local_pos.x() - was.x(),
                                   local_pos.y() - was.y())
                else:
                    leader.tip = QPointF(local_pos)
                # What the leader points at has been moved: the hinge follows
                # it round rather than staying on a side that no longer faces
                # it.
                self.leader_moved()
                self.geometryChanged.emit()
            else:
                self.set_elbow_of(leader, local_pos)
            return
        if self.leaders:
            # Resizing the box must not drag the arrows along with it: each
            # points at something on the page, and stays pointing at it until
            # it is moved on purpose.
            pinned = [(self.mapToScene(leader.tip),
                       [self.mapToScene(p) for p in leader.cloud])
                      for leader in self.leaders]
            super().move_handle(key, local_pos, keep_ratio)
            self.prepareGeometryChange()
            for leader, (tip, cloud) in zip(self.leaders, pinned):
                leader.tip = self.mapFromScene(tip)
                leader.cloud = [self.mapFromScene(p) for p in cloud]
            self.leader_moved()
            return
        super().move_handle(key, local_pos, keep_ratio)

    # -- editing -----------------------------------------------------------
    def begin_edit(self) -> None:
        if self.locked:
            return
        # The fields come back as they were typed, so they can be edited
        # rather than having their answers typed over.
        if self.has_fields() and self.doc.toPlainText() != self.written:
            self.doc.setPlainText(self.written)
        self.check_spelling(True)
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

    def check_spelling(self, on: bool) -> None:
        """Underline misspelt words — while they are being typed, and only then.

        The squiggle is a hint to whoever is writing, not part of the drawing,
        so it goes away with the caret and never reaches the printed page.
        """
        if on and self._speller is None:
            from ..ui import preferences
            if not preferences.current().check_spelling:
                return
            from ..core.spelling import shared
            if not shared().ready():
                return
            self._speller = _SpellHighlighter(self.doc)
        elif not on and self._speller is not None:
            self._speller.setDocument(None)
            self._speller = None

    def end_edit(self) -> None:
        self.written = self.doc.toPlainText()
        self.check_spelling(False)
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
            "written": self.written,
            "digits": self.digits,
        })
        if self.leaders:
            data["leaders"] = [leader.to_dict() for leader in self.leaders]
        return data

    def deserialize(self, data: dict) -> None:
        values = data.get("rect", [0, 0, 160, 50])
        self._rect = QRectF(*values)
        self.auto_size = bool(data.get("auto_size", True))
        stored = data.get("leaders")
        if stored is not None:
            self.leaders = [_Leader.from_dict(entry) for entry in stored]
        else:
            # Written before a box could have more than one arrow: a single
            # tip, with the reach kept beside it rather than in it.
            points = data.get("leader")
            reach = float(data.get("elbow_reach", self.ELBOW_REACH))
            if points:
                self.leaders = [_Leader(QPointF(float(points[0][0]),
                                                float(points[0][1])), "", reach)]
            elif points is not None:
                self.leaders = []
        self.load_base(data)
        html = data.get("html")
        if html:
            self.doc.setHtml(html)
        else:
            self.doc.setPlainText(data.get("text", ""))
        self.digits = int(data.get("digits", 4))
        self.written = data.get("written") or self.doc.toPlainText()
        self.apply_style()


@register_item
class TextItem(_TextBase):
    """A free text box with optional border and fill."""

    TYPE = "text"
    NAME = "Text box"

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        self.paint_leader(painter)
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
class TypewriterItem(TextItem):
    """Words straight onto the page, with no box around them.

    Bluebeam's typewriter: for filling in a form, writing on a drawing, or
    adding a line to a title block, where a border and a white fill would be
    in the way. It is a text box in every other respect — it is only the
    default look that differs, and either can be changed afterwards.
    """

    TYPE = "typewriter"
    NAME = "Typewriter"

    def __init__(self, text: str = "", rect: Optional[QRectF] = None):
        super().__init__(text, rect)
        self.style.stroke = ""
        self.style.fill = ""
        self.style.fill_opacity = 0.0
        self.style.width = 0.0
        self.style.text_color = "#111318"


@register_item
class FlagItem(MarkupItem):
    """A small flag pinned to a spot, for marking somewhere to come back to."""

    TYPE = "flag"
    NAME = "Flag"
    RESIZABLE = False
    ROTATABLE = False
    WIDTH = 18.0
    HEIGHT = 22.0

    def __init__(self, comment: str = ""):
        super().__init__()
        self.comment = comment
        self.style = Style(stroke="#c92a2a", fill="#c92a2a", fill_opacity=1.0,
                           width=1.0)

    def local_rect(self) -> QRectF:
        return QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        pole = QPen(QColor(self.style.stroke or "#c92a2a"))
        pole.setWidthF(max(self.style.width, 0.8))
        painter.setPen(pole)
        painter.drawLine(QPointF(2, 0), QPointF(2, self.HEIGHT))
        colour = QColor(self.style.fill or self.style.stroke or "#c92a2a")
        colour.setAlphaF(max(0.0, min(1.0, self.style.fill_opacity * self.style.opacity)))
        painter.setBrush(QBrush(colour))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(QPolygonF([QPointF(2.6, 1), QPointF(self.WIDTH, 5.5),
                                       QPointF(2.6, 10)]))

    def summary(self) -> str:
        return self.comment.replace("\n", " ")[:160]

    def serialize(self) -> dict:
        return self.base_dict()


@register_item
class CalloutItem(_TextBase):
    """A text box with a leader pointing at something.

    The leader joins the box at the middle of one of its four sides — chosen
    from where the arrow is, so it always leaves the box on the side facing
    what it points at — and leaves that side square on. The elbow is worked
    out from that, but it can be slid in and out along the same perpendicular,
    which is the one thing about it worth deciding by hand.
    """

    TYPE = "callout"
    NAME = "Callout"

    SHAPES = ("box", "cloud")
    ELBOW_REACH = 24.0          # how far the elbow stands off the box by default

    def __init__(self, text: str = "", rect: Optional[QRectF] = None,
                 leader: Optional[list[QPointF]] = None, shape: str = "box"):
        super().__init__(text, rect)
        self.shape_kind = shape if shape in self.SHAPES else "box"
        self.cloud_radius = 9.0
        # The region a cloud call-out is about lives on the leader that points
        # at it, not on the call-out — because a call-out can have several
        # leaders, and each of them is either an arrow at a place or a cloud
        # round a region. One markup either way: moved, copied, coloured and
        # kept in a tool set as one thing, because it is one thing.
        self.style.arrow_end = "arrow"
        self.leader_shown = True
        points = [QPointF(p) for p in (leader or [])]
        if points:
            self.tip = QPointF(points[0])

    # -- the clouded region ------------------------------------------------
    def clouds_a_region(self) -> bool:
        return any(leader.clouds() for leader in self.leaders)

    def cloud_leader(self):
        """The first leader that clouds something, if there is one."""
        for leader in self.leaders:
            if leader.clouds():
                return leader
        return None

    @property
    def cloud_points(self) -> list:
        """The first clouded region — the spelling everything else knows."""
        leader = self.cloud_leader()
        return leader.cloud if leader is not None else []

    @cloud_points.setter
    def cloud_points(self, points) -> None:
        self.set_cloud(points)

    def set_cloud(self, points) -> None:
        """Cloud a region, or stop clouding one.

        The region goes on a leader of its own, so a call-out can point at one
        thing with an arrow and at another with a cloud at the same time. A
        cloud leader has no arrow head — the cloud is what does the pointing,
        and the line only says which note belongs to which cloud — but that is
        decided when it is drawn, not by taking the heads off every leader the
        call-out has.
        """
        self.prepareGeometryChange()
        wanted = [QPointF(p) for p in (points or [])]
        leader = self.cloud_leader()
        if len(wanted) < 3:
            if leader is not None:
                self.leaders.remove(leader)
            self.geometryChanged.emit()
            return
        if leader is None:
            middle = QPointF(sum(p.x() for p in wanted) / len(wanted),
                             sum(p.y() for p in wanted) / len(wanted))
            leader = _Leader(middle, "", self.ELBOW_REACH, "cloud", wanted)
            self.leaders.append(leader)
        else:
            leader.cloud = wanted
        self.leader_moved()
        self.geometryChanged.emit()

    def add_cloud_leader(self, points) -> "_Leader":
        """Another leader, clouding *points*, beside whatever is already there."""
        self.prepareGeometryChange()
        wanted = [QPointF(p) for p in (points or [])]
        middle = (QPointF(sum(p.x() for p in wanted) / len(wanted),
                          sum(p.y() for p in wanted) / len(wanted))
                  if wanted else QPointF(self._rect.center()))
        leader = _Leader(middle, "", self.ELBOW_REACH, "cloud", wanted)
        self.leaders.append(leader)
        self.leader_moved()
        self.geometryChanged.emit()
        return leader

    def set_cloud_rect(self, rect: Optional[QRectF]) -> None:
        """Cloud a rectangle — the four corners of one."""
        if rect is None:
            self.set_cloud([])
            return
        box = QRectF(rect).normalized()
        self.set_cloud([box.topLeft(), box.topRight(),
                        box.bottomRight(), box.bottomLeft()])

    def cloud_box(self) -> QRectF:
        """The rectangle the first clouded region sits in."""
        leader = self.cloud_leader()
        return leader.cloud_box() if leader is not None else QRectF()

    def cloud_join(self) -> QPointF:
        """Where the line meets the cloud: its nearest corner or edge middle."""
        leader = self.cloud_leader()
        if leader is None:
            return QPointF()
        return leader.join_nearest(self._rect.normalized().center())

    def box_join(self) -> QPointF:
        """Where the line leaves the note: the middle of the side facing the cloud."""
        leader = self.cloud_leader()
        if leader is None:
            return self._rect.normalized().center()
        return self.side_point_of(leader)

    def cloud_polygon(self):
        from PySide6.QtGui import QPolygonF

        return QPolygonF(list(self.cloud_points))

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Every leader, clouds and arrows alike: they are the same thing drawn
        # two ways, so they are drawn in the same place by the same code.
        self.paint_leader(painter)
        rect = self._rect.normalized()
        painter.setBrush(self.style.brush())
        painter.setPen(self.style.pen())
        if self.shape_kind == "cloud":
            from .base import cloud_path
            painter.drawPath(cloud_path(self.cloud_polygon_of(rect),
                                        self.cloud_radius))
        else:
            painter.drawRoundedRect(rect, self.style.corner_radius,
                                    self.style.corner_radius)
        self.paint_text(painter)

    @staticmethod
    def cloud_polygon_of(rect: QRectF):
        from PySide6.QtGui import QPolygonF

        return QPolygonF([rect.topLeft(), rect.topRight(),
                          rect.bottomRight(), rect.bottomLeft()])

    def boundingRect(self) -> QRectF:
        rect = super().boundingRect()
        radius = self.cloud_radius
        if self.shape_kind == "cloud":
            rect = rect.adjusted(-radius, -radius, radius, radius)
        for leader in self.leaders:
            if leader.clouds():
                rect = rect.united(leader.cloud_box().adjusted(
                    -radius - 2, -radius - 2, radius + 2, radius + 2))
        return rect

    def handle_points(self) -> dict[str, QPointF]:
        handles = super().handle_points()
        # Every corner of every cloud is its own handle, so a shape drawn
        # point by point can be adjusted point by point. The key says which
        # leader's cloud and which corner of it.
        for which, leader in enumerate(self.leaders):
            for index, point in enumerate(leader.cloud):
                handles[f"c{which}_{index}"] = QPointF(point)
        return handles

    def leader_handles(self) -> set[str]:
        keys = super().leader_handles()
        for which, leader in enumerate(self.leaders):
            keys |= {f"c{which}_{index}" for index in range(len(leader.cloud))}
        return keys

    def cloud_point_at(self, key: str):
        """The leader and the corner of its cloud a handle key names."""
        if not key.startswith("c") or "_" not in key:
            return None, -1
        which, _, index = key[1:].partition("_")
        if not (which.isdigit() and index.isdigit()):
            return None, -1
        which, index = int(which), int(index)
        if 0 <= which < len(self.leaders):
            leader = self.leaders[which]
            if 0 <= index < len(leader.cloud):
                return leader, index
        return None, -1

    def move_handle(self, key: str, local_pos: QPointF,
                    keep_ratio: bool = False) -> None:
        leader, corner = self.cloud_point_at(key)
        if leader is not None:
            self.prepareGeometryChange()
            leader.cloud[corner] = QPointF(local_pos)
            self.geometryChanged.emit()
            return
        super().move_handle(key, local_pos, keep_ratio)

    def serialize(self) -> dict:
        data = super().serialize()
        data["shape_kind"] = self.shape_kind
        data["cloud_radius"] = self.cloud_radius
        # The region travels on its leader now. This is written as well so a
        # file saved here still opens in a version that expects it there.
        if self.cloud_points:
            data["cloud_points"] = [[p.x(), p.y()] for p in self.cloud_points]
        return data

    def deserialize(self, data: dict) -> None:
        super().deserialize(data)
        self.shape_kind = data.get("shape_kind", "box")
        self.cloud_radius = float(data.get("cloud_radius", 9.0))
        if self.clouds_a_region():
            return                    # it came in on its leader, as it should
        points = data.get("cloud_points")
        if points:
            self.set_cloud([QPointF(float(p[0]), float(p[1])) for p in points])
        else:
            stored = data.get("cloud_rect")       # written before it was a shape
            if stored:
                self.set_cloud_rect(QRectF(*stored))

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
