"""Revu's alignment commands (Revu 21: Tools ▸ Align Markups; the Alignment
toolbar; a selection's right-click ▸ Alignment).

- Align Left, Centre, Right, Top, Middle, Bottom (two or more): each markup
  to the *primary* markup's edge or centre line. The primary is the first
  markup picked: its control points are yellow, the others' green, and a
  click on a green-pointed markup makes it the primary (ui/scene.py).
- Align Width, Height and Size (two or more): each the primary's width,
  height or both, its top left corner staying where it is.
- Distribute Horizontally and Vertically (three or more): the centres
  equally spaced between the two outermost, which stay.
- Centre in Document (one or more): each markup's centre to its page's.
- Flip Horizontal and Vertical (one or more that flip): each about its own
  centre — images, snapshots, stamps, polylines, polygons, clouds, pen and
  highlighter ink, and groups of them (a group is flipped as one, about its
  middle). A callout's box goes to the other side of its leader, the words
  still readable; a text box does not flip.

Each command is greyed until enough is picked (refresh, on every change of
the selection).

A group is one thing to align, as in Revu, and a calculation block takes the
equations in it along. Each command is one undo step.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QImage, QTransform

from ..items.base import MarkupItem

#: command key → (menu label, what it does, how many it needs). The keys are
#: the window's actions (act_<key>) and their command ids (command.<key>).
COMMANDS = {
    "align_left": ("Align Left", "Line the left edges up with the primary markup's", 2),
    "align_hcenter": ("Align Centre", "Line the centres up, across, with the primary "
                                      "markup's", 2),
    "align_right": ("Align Right", "Line the right edges up with the primary markup's", 2),
    "align_top": ("Align Top", "Line the tops up with the primary markup's", 2),
    "align_vcenter": ("Align Middle", "Line the middles up, down the page, with the "
                                      "primary markup's", 2),
    "align_bottom": ("Align Bottom", "Line the bottoms up with the primary markup's", 2),
    "align_width": ("Align Width", "Make each the primary markup's width", 2),
    "align_height": ("Align Height", "Make each the primary markup's height", 2),
    "align_size": ("Align Size", "Make each the primary markup's width and height", 2),
    "distribute_horizontally": ("Distribute Horizontally",
                                "Space the centres equally across, between the two "
                                "outermost", 3),
    "distribute_vertically": ("Distribute Vertically",
                              "Space the centres equally down, between the two "
                              "outermost", 3),
    "centre_in_document": ("Centre in Document", "Put each markup's centre on the "
                                                 "centre of its page", 1),
    "flip_horizontal": ("Flip Horizontal", "Mirror each, left to right, about its "
                                           "own centre", 1),
    "flip_vertical": ("Flip Vertical", "Mirror each, top to bottom, about its own "
                                       "centre", 1),
}

#: The toolbar and the menus, in Revu's order, None a separator.
ORDER = ("align_left", "align_hcenter", "align_right", "align_top", "align_vcenter",
         "align_bottom", None, "align_width", "align_height", "align_size", None,
         "distribute_horizontally", "distribute_vertically", None,
         "centre_in_document", None, "flip_horizontal", "flip_vertical")

#: Each command's icon (ui/icons.py).
ICONS = {key: key for key in COMMANDS}

FLIPPABLE = ("images, snapshots, stamps, callouts, polylines, polygons, clouds, pen and "
             "highlighter ink")


def needs(count: int) -> str:
    return {1: "one markup or more", 2: "two markups or more",
            3: "three markups or more"}[count]


# ---------------------------------------------------------------------------
# what is picked, as things to align
# ---------------------------------------------------------------------------
class Unit:
    """One thing to align: a markup, a group, or a calculation block with its
    equations."""

    def __init__(self, members: list):
        self.members = members

    def scene_rect(self) -> QRectF:
        """Where it is on the canvas: the shapes' own boxes, not the room
        their lines, handles and captions take round them."""
        box = QRectF()
        for member in self.members:
            rect = shape_rect(member)
            box = rect if box.isNull() else box.united(rect)
        return box

    def frame(self):
        return self.members[0].parentItem()

    def move_by(self, delta: QPointF) -> None:
        """Move every member *delta* on the canvas."""
        if delta.isNull():
            return
        for member in self.members:
            parent = member.parentItem()
            step = delta if parent is None else \
                parent.mapFromScene(delta) - parent.mapFromScene(QPointF(0, 0))
            member.setPos(member.pos() + step)
            if hasattr(member, "touch"):
                member.touch()


def shape_rect(item) -> QRectF:
    """*item*'s own box on the canvas."""
    local = item.local_rect().normalized() if hasattr(item, "local_rect") else QRectF()
    if local.isEmpty():
        local = item.bounds_without_chrome()
    return item.mapRectToScene(local)


def _family(window, item) -> list:
    from ..items.calc import with_block_members
    return with_block_members(window.view.group_of(item))


def units(window) -> list:
    """The selection as things to align, the primary's first, then in the
    order they were picked."""
    view = window.view
    scene = view.scene()
    if scene is None:
        return []
    order = scene.picked_in_order() if hasattr(scene, "picked_in_order") else \
        window.selected_items()
    found, seen = [], set()
    for item in order:
        if not isinstance(item, MarkupItem) or id(item) in seen or not view.editable(item) \
                or getattr(item, "SHEET_RUN", False):
            continue
        members = [m for m in _family(window, item)
                   if id(m) not in seen and view.editable(m)]
        if not members:
            continue
        seen.update(id(m) for m in members)
        found.append(Unit(members))
    return found


def unit_count(window, flippable: bool = False) -> int:
    """How many things are picked, cheaply (the actions' state); with
    *flippable*, how many of them a flip would turn over."""
    scene = window.view.scene()
    if scene is None:
        return 0
    view = window.view
    names, count = set(), 0
    for item in scene.selectedItems():
        if not isinstance(item, MarkupItem) or getattr(item, "SHEET_RUN", False) \
                or not view.editable(item):
            continue
        if flippable and not _flippable(item):
            continue
        if item.group:
            if item.group in names:
                continue
            names.add(item.group)
        count += 1
    return count


def refresh(window) -> None:
    """Each command offered when enough is picked, its tip saying what it
    wants when not (the actions on the toolbar, Edit ▸ Alignment and the
    right-click menu are the same)."""
    count = unit_count(window)
    flips = unit_count(window, flippable=True)
    for key, (label, tip, least) in COMMANDS.items():
        action = getattr(window, f"act_{key}", None)
        if action is None:
            continue
        flip = key.startswith("flip_")
        enough = (flips if flip else count) >= least
        if action.isEnabled() != enough:
            action.setEnabled(enough)
        if enough:
            words = f"{label} — {tip}"
        elif flip and count:
            words = f"{label} — only {FLIPPABLE} flip; text boxes do not. {tip}"
        else:
            words = f"{label} — select {needs(least)} first. {tip}"
        if least >= 2 and enough:
            words += " (the primary: the first picked, yellow points; click a "\
                     "green-pointed one to make it the primary)"
        action.setToolTip(words)
        action.setStatusTip(words)


# ---------------------------------------------------------------------------
# the commands
# ---------------------------------------------------------------------------
def run(window, key: str) -> bool:
    """Do *key* to the selection as one undo step. False (and the status
    line says why) when there is not enough picked."""
    label, _tip, least = COMMANDS[key]
    found = units(window)
    if len(found) < least:
        window.status_hint.setText(f"{label}: select {needs(least)} first")
        return False
    view = window.view
    view.begin_snapshot(view.involved_frames(*[m for u in found for m in u.members]))
    if key.startswith("align_") and key[6:] in ("left", "hcenter", "right", "top",
                                                  "vcenter", "bottom"):
        _align(found, key[6:])
    elif key in ("align_width", "align_height", "align_size"):
        _same_size(window, found, key[6:])
    elif key.startswith("distribute_"):
        _distribute(found, key == "distribute_horizontally")
    elif key == "centre_in_document":
        _centre_on_page(found)
    else:
        flipped = _flip(window, found, key == "flip_horizontal")
        if not flipped:
            view.commit_snapshot(label)
            window.status_hint.setText(f"{label}: only {FLIPPABLE} and groups of them "
                                       "flip")
            return False
    view.commit_snapshot(label)
    window.refresh_selection()
    return True


def _align(found: list, edge: str) -> None:
    target = found[0].scene_rect()
    for unit in found[1:]:
        rect = unit.scene_rect()
        delta = QPointF(0, 0)
        if edge == "left":
            delta.setX(target.left() - rect.left())
        elif edge == "right":
            delta.setX(target.right() - rect.right())
        elif edge == "hcenter":
            delta.setX(target.center().x() - rect.center().x())
        elif edge == "top":
            delta.setY(target.top() - rect.top())
        elif edge == "bottom":
            delta.setY(target.bottom() - rect.bottom())
        elif edge == "vcenter":
            delta.setY(target.center().y() - rect.center().y())
        unit.move_by(delta)


def _distribute(found: list, across: bool) -> None:
    def centre(unit) -> float:
        middle = unit.scene_rect().center()
        return middle.x() if across else middle.y()
    ordered = sorted(found, key=centre)
    first, last = centre(ordered[0]), centre(ordered[-1])
    step = (last - first) / (len(ordered) - 1)
    for number, unit in enumerate(ordered[1:-1], start=1):
        shift = first + step * number - centre(unit)
        unit.move_by(QPointF(shift, 0) if across else QPointF(0, shift))


def _centre_on_page(found: list) -> None:
    for unit in found:
        frame = unit.frame()
        if frame is None or not hasattr(frame, "page_rect"):
            continue
        page = frame.mapRectToScene(frame.page_rect()).center()
        unit.move_by(page - unit.scene_rect().center())


# -- sizes -----------------------------------------------------------------------
def _resizable(item) -> bool:
    if getattr(item, "IS_CALC", False) or getattr(item, "TYPE", "") in (
            "calc_block", "calc_text", "table", "sheet_run", "count", "note", "flag"):
        return False                     # their size is their content's
    points = getattr(item, "points", None)
    if isinstance(points, list) and len(points) >= 2:
        return True
    return hasattr(item, "set_local_rect")


def _scale_item(item, sx: float, sy: float) -> None:
    """Make *item* *sx* times as wide and *sy* times as tall, in its own
    coordinates, its top left staying where it was."""
    item.prepareGeometryChange()
    points = getattr(item, "points", None)
    if isinstance(points, list) and len(points) >= 2:
        corner = item.local_rect().normalized().topLeft()

        def scaled(p: QPointF) -> QPointF:
            return QPointF(corner.x() + (p.x() - corner.x()) * sx,
                           corner.y() + (p.y() - corner.y()) * sy)
        item.points = [scaled(p) for p in points]
        bezier = getattr(item, "bezier", None)
        if bezier:
            item.bezier = {k: (scaled(a), scaled(b)) for k, (a, b) in bezier.items()}
    else:
        rect = item.local_rect().normalized()
        item.set_local_rect(QRectF(rect.x(), rect.y(), max(rect.width() * sx, 1.0),
                                   max(rect.height() * sy, 1.0)))
    turn = getattr(item, "_turn_about_centre", None)
    if turn is not None:
        turn()
    if hasattr(item, "touch"):
        item.touch()
    if hasattr(item, "apply_style"):
        item.apply_style()
    signal = getattr(item, "geometryChanged", None)
    if signal is not None:
        signal.emit()
    item.update()


def _same_size(window, found: list, which: str) -> None:
    target = found[0].scene_rect()
    skipped = 0
    for unit in found[1:]:
        rect = unit.scene_rect()
        if rect.width() <= 1e-6 or rect.height() <= 1e-6:
            continue
        sx = target.width() / rect.width() if which in ("width", "size") else 1.0
        sy = target.height() / rect.height() if which in ("height", "size") else 1.0
        if not all(_resizable(m) for m in unit.members):
            skipped += 1
            continue
        corner = rect.topLeft()
        for member in unit.members:
            # a group's members keep their places in it, in proportion
            before = shape_rect(member).topLeft()
            _scale_item(member, sx, sy)
            after = shape_rect(member).topLeft()
            wanted = QPointF(corner.x() + (before.x() - corner.x()) * sx,
                             corner.y() + (before.y() - corner.y()) * sy)
            Unit([member]).move_by(wanted - after)
    if skipped:
        window.status_hint.setText(
            f"{skipped} left its size: an equation, a table, a note or a count is the "
            "size of what it holds")


# -- flips -----------------------------------------------------------------------
def _flippable(item) -> bool:
    """Revu's: images, snapshots, stamps, callouts (their words stay
    readable), polylines, polygons, clouds, pen and highlighter ink. Not a
    text box."""
    kind = getattr(item, "TYPE", "")
    if kind in ("image", "stamp", "snapshot"):
        return True
    if kind == "callout":
        return bool(getattr(item, "leaders", None))
    points = getattr(item, "points", None)
    return kind == "poly" and isinstance(points, list) and len(points) >= 2


def _keep_centre(item, centre: QPointF, before: QPointF) -> None:
    """Move *item* so its own point *centre* is back at *before* on the
    canvas."""
    Unit([item]).move_by(before - item.mapToScene(centre))


def _mirror_local(item, across: bool) -> None:
    """Mirror *item* in its own coordinates about the middle of its box, and
    turn it the other way, which is the page's mirror image of it."""
    centre = item.local_rect().normalized().center()

    def mirrored(p: QPointF) -> QPointF:
        return QPointF(2 * centre.x() - p.x(), p.y()) if across else \
            QPointF(p.x(), 2 * centre.y() - p.y())
    before = item.mapToScene(centre)
    item.prepareGeometryChange()
    kind = getattr(item, "TYPE", "")
    if kind == "poly":
        item.points = [mirrored(p) for p in item.points]
        if item.curved:
            # a bow is to one side of its side's way round: mirrored, the other
            item.curved = {k: (-bow, along) for k, (bow, along) in item.curved.items()}
        if item.bezier:
            item.bezier = {k: (mirrored(a), mirrored(b)) for k, (a, b) in item.bezier.items()}
    elif kind == "stamp":
        # its picture and its words, mirrored as Revu's are: about the middle
        # of its box, before anything else it has (saved with it, and drawn
        # so into the PDF's appearance)
        mirror = (QTransform.fromTranslate(-centre.x(), -centre.y())
                  * QTransform.fromScale(-1.0 if across else 1.0, 1.0 if across else -1.0)
                  * QTransform.fromTranslate(centre.x(), centre.y()))
        item.setTransform(mirror * item.transform())
    if item.rotation():
        item.setRotation(-item.rotation())
    _keep_centre(item, centre, before)
    if hasattr(item, "touch"):
        item.touch()
    signal = getattr(item, "geometryChanged", None)
    if signal is not None:
        signal.emit()
    item.update()


def _mirror_picture(window, item, across: bool) -> None:
    """An image: its picture mirrored, kept as a picture of its own (so the
    PDF and every reader show it mirrored), and the part shown with it."""
    data = window.document.asset(item.asset_key)
    picture = QImage()
    if not data or not picture.loadFromData(bytes(data)):
        return
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    flipped = picture.mirrored(across, not across)
    out = QByteArray()
    buffer = QBuffer(out)
    buffer.open(QIODevice.WriteOnly)
    flipped.save(buffer, "PNG")
    item.asset_key = window.document.add_asset(bytes(out), ".png")
    crop = item.crop
    item.crop = QRectF(1 - crop.x() - crop.width(), crop.y(), crop.width(), crop.height()) \
        if across else QRectF(crop.x(), 1 - crop.y() - crop.height(), crop.width(),
                              crop.height())
    item.load_from_document(window.document)
    if item.rotation():
        centre = item.local_rect().normalized().center()
        before = item.mapToScene(centre)
        item.setRotation(-item.rotation())
        _keep_centre(item, centre, before)
    item.touch()
    item.update()


def _turn_callout(item, across: bool) -> None:
    """A callout as Revu flips one: the box goes to the other side of its
    leaders and the leaders are mirrored, but the words are not — they stay
    readable."""
    box = item.local_rect().normalized()
    xs, ys = [box.left(), box.right()], [box.top(), box.bottom()]
    for leader in item.leaders:
        for point in [leader.tip] + list(leader.cloud):
            xs.append(point.x())
            ys.append(point.y())
    # the middle of the box and its leaders together, which stays put
    centre = QPointF((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)

    def mirrored(p: QPointF) -> QPointF:
        return QPointF(2 * centre.x() - p.x(), p.y()) if across else \
            QPointF(p.x(), 2 * centre.y() - p.y())
    item.prepareGeometryChange()
    for leader in item.leaders:
        leader.tip = mirrored(leader.tip)
        leader.cloud = [mirrored(p) for p in leader.cloud]
        swaps = {"left": "right", "right": "left"} if across else \
            {"top": "bottom", "bottom": "top"}
        leader.side = swaps.get(leader.side, leader.side)
    item.set_local_rect(QRectF(mirrored(box.topLeft()), mirrored(box.bottomRight()))
                        .normalized())
    item.touch()
    signal = getattr(item, "geometryChanged", None)
    if signal is not None:
        signal.emit()
    item.update()


def _mirror_snapshot(item, across: bool) -> None:
    """A snapshot's drawing mirrored in its box (items/snapshot.py keeps
    which way it is turned, and draws, prints and exports it so)."""
    centre = item.local_rect().normalized().center()
    before = item.mapToScene(centre)
    item.mirror(across)
    if item.rotation():
        item.setRotation(-item.rotation())
        _keep_centre(item, centre, before)
    item.touch()


def _flip(window, found: list, across: bool) -> int:
    """Flip what can be; how many were."""
    done = 0
    for unit in found:
        members = [m for m in unit.members if _flippable(m)]
        if not members:
            continue
        middle = unit.scene_rect().center()
        for member in members:
            kind = getattr(member, "TYPE", "")
            if kind == "image":
                _mirror_picture(window, member, across)
            elif kind == "callout":
                _turn_callout(member, across)
            elif kind == "snapshot":
                _mirror_snapshot(member, across)
            else:
                _mirror_local(member, across)
        if len(unit.members) > 1:
            # a group mirrored as one: each member to the other side of its
            # middle (those that cannot flip still change sides)
            for member in unit.members:
                centre = shape_rect(member).center()
                goal = QPointF(2 * middle.x() - centre.x(), centre.y()) if across else \
                    QPointF(centre.x(), 2 * middle.y() - centre.y())
                Unit([member]).move_by(goal - centre)
        done += 1
    return done
