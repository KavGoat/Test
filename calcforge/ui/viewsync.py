"""Window Sync: the two views of a Split View (and other windows showing the
same document) kept in step, as Revu's Sync keeps its split views.

- **Sync off**: each view is its own. Nothing done in one — a zoom, a scroll,
  a page turned, the split resized — moves the other.
- **Page sync**: zoom and position only; which page does not matter (the
  user, 2026-10-19: "x, y and zoom relative to whatever page is in focus,
  no matter what"). Each view stays on its own page; when one zooms or
  scrolls, the other takes the same zoom and shows the same spot of *its*
  page in focus — the same points from the page's top left corner, as the
  page lies on screen (turned pages included), so pages of different sizes
  line up at the same physical spot. A spot past the edge of a smaller page
  stops at that edge; desk showing beyond a page's edge shows beyond the
  other's edge too. Going to another page in one view leaves the other on
  its page (at the same spot of it); scrolling on across a page boundary
  carries the other across its own boundary with it.
- **Document sync**: the views are locked together. A scroll, zoom or page
  change in one is repeated in the other by the same relative amount, across
  two different documents too.

Document sync keeps one rule, so that nothing echoes back, drifts or
jitters. Where a view is looking is a *place*: the page under the middle of
the view, that point as a share of the page's width and height as it lies
on the canvas, and the zoom. When two views are linked (the sync chosen, a
document shown in either) the difference between their places is noted — so
many pages on, so far across and down the page, so much larger — and from
then on, whichever view moves, the other is put at its place plus that
difference. Page sizes and turns differ from document to document; shares
of the page do not. A view that cannot follow (it has fewer pages, or is at
the zoom limit) stays as near as it can and comes back into step as soon as
the other comes back.

Page sync keeps which page each view is on (its page in focus) rather than
reading it afresh from the middle of the view each time, so a view sitting
in the gap between two pages does not flip between them.

Whatever is being repeated is repeated once: while one view's move is being
carried to the others, nothing they do in turn is carried anywhere.
"""
from __future__ import annotations

import weakref
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QPointF, QRectF

#: the status bar's Sync box, in its order
OFF, PAGE, DOCUMENT = 0, 1, 2


@dataclass(frozen=True)
class Place:
    """Where a view is looking."""
    page: int
    across: float        # the middle of the view, as a share of the page's width
    down: float          # ... and of its height
    zoom: float


@dataclass(frozen=True)
class Link:
    """How far apart two linked views are: the second's place less the
    first's (the zoom as a ratio)."""
    pages: int
    across: float
    down: float
    zoom: float

    def onward(self, place: Place) -> Place:
        return Place(place.page + self.pages, place.across + self.across,
                     place.down + self.down, place.zoom * self.zoom)

    def reversed(self) -> "Link":
        return Link(-self.pages, -self.across, -self.down,
                    1.0 / self.zoom if self.zoom else 1.0)


def _frames(view) -> list:
    scene = view.scene() if view is not None else None
    return list(getattr(scene, "frames", None) or [])


def page_box(frame) -> QRectF:
    """A page as it lies on the canvas (turned, if it is turned)."""
    return frame.mapRectToScene(frame.page_rect()).normalized()


def middle_of(view) -> QPointF:
    return QPointF(view.viewport().rect().center())


def place_of(view) -> Optional[Place]:
    """Where *view* is looking, or None with nothing in it."""
    frames = _frames(view)
    if not frames:
        return None
    point = view.viewportTransform().inverted()[0].map(middle_of(view))
    frame = view.scene().frame_at(point)
    if frame not in frames:
        return None
    box = page_box(frame)
    if box.width() <= 0 or box.height() <= 0:
        return None
    return Place(frames.index(frame), (point.x() - box.left()) / box.width(),
                 (point.y() - box.top()) / box.height(), view.zoom())


def link_between(first, second) -> Optional[Link]:
    a, b = place_of(first), place_of(second)
    if a is None or b is None or a.zoom <= 0:
        return None
    return Link(b.page - a.page, b.across - a.across, b.down - a.down, b.zoom / a.zoom)


def reachable(view, place: Place) -> Place:
    """*place*, kept to the pages *view* has: past its last page, the foot of
    its last page; before its first, the head of its first."""
    count = len(_frames(view))
    if place.page > count - 1:
        return Place(count - 1, place.across, max(place.down, 1.0), place.zoom)
    if place.page < 0:
        return Place(0, place.across, min(place.down, 0.0), place.zoom)
    return place


def put(view, place: Place) -> None:
    """Show *place* in *view*: its zoom, and the point at its middle. The
    page has to be on the canvas already (Single Page shows one)."""
    frames = _frames(view)
    if not frames:
        return
    place = reachable(view, place)
    view.set_zoom(place.zoom)
    box = page_box(frames[place.page])
    view.bring_to(QPointF(box.left() + place.across * box.width(),
                          box.top() + place.down * box.height()), middle_of(view))


def focus_page(view) -> Optional[int]:
    """The page under the middle of *view* (the nearest, on the desk)."""
    frames = _frames(view)
    if not frames:
        return None
    point = view.viewportTransform().inverted()[0].map(middle_of(view))
    frame = view.scene().frame_at(point)
    return frames.index(frame) if frame in frames else None


def same_spot(offset: float, size: float, other_size: float) -> float:
    """Page sync, along one side: the spot *offset* points into a page
    *size* long, on a page *other_size* long. On the page it is the same
    number of points in, stopping at the edge of a shorter page; on the
    desk before the page it is as far before; on the desk past its end, as
    far past the other's end."""
    if offset < 0:
        return offset
    if offset > size:
        return other_size + (offset - size)
    return min(offset, other_size)


def one_page_at_a_time(view) -> bool:
    return getattr(view.scene(), "page_mode", "continuous") in ("single", "side")


class Follower:
    """A view that follows another: the other view of the split, or the view
    of another window showing the same document."""

    def __init__(self, window, view, pane=None):
        self.window = window       # the window the view is in
        self.view = view
        self.pane = pane           # its pane, when it is not the window's view in hand

    @property
    def in_hand(self) -> bool:
        return self.view is self.window.view

    def bring_page_on(self, index: int) -> None:
        """In Single Page (or Side-by-Side), page *index* comes onto the
        canvas before the view is put on it."""
        frames = _frames(self.view)
        if not frames or not one_page_at_a_time(self.view):
            return
        index = max(0, min(index, len(frames) - 1))
        if frames[index].isVisible():
            return
        if self.in_hand:
            self.window.go_to_page(index)
            return
        self.view.scene().show_page(index)
        self.view._shown_page = index
        self._note_page(index)

    def _note_page(self, index: int) -> None:
        if self.pane is not None and self.pane.documents:
            state = self.pane.documents[self.pane.active]
            if state.get("scene") is self.view.scene():
                state["index"] = index


class ViewSync:
    """A window's Window Sync: which views follow which, and the links."""

    #: a move being carried to other views, anywhere: what those views do in
    #: turn is not carried back (A moves B moves A)
    _carrying = False
    #: (first view, second view) -> (the two views, their canvases then, the Link)
    _links: dict = {}
    #: Page sync: each view's page in focus -> (its canvas then, the page)
    _focus = weakref.WeakKeyDictionary()
    #: a page gone to (not scrolled onto) is being shown: Page sync leaves
    #: the other view on its own page
    _jumping = False

    def __init__(self, window):
        self._window = weakref.ref(window)

    @property
    def window(self):
        return self._window()

    def mode(self) -> int:
        window = self.window
        box = getattr(window, "window_sync", None) if window is not None else None
        return box.currentIndex() if box is not None else OFF

    # -- quiet spells --------------------------------------------------------
    @classmethod
    @contextmanager
    def quiet(cls):
        """Nothing moved inside is carried to another view."""
        was, cls._carrying = cls._carrying, True
        try:
            yield
        finally:
            cls._carrying = was

    @classmethod
    def carrying(cls) -> bool:
        return cls._carrying

    @classmethod
    @contextmanager
    def jumping(cls):
        """A page gone to — Thumbnails, the page box, a key, a bookmark, a
        link, a Find result — rather than scrolled onto."""
        was, cls._jumping = cls._jumping, True
        try:
            yield
        finally:
            cls._jumping = was

    # -- Page sync: the page each view is on ---------------------------------
    @classmethod
    def _page_in_focus(cls, view) -> Optional[int]:
        frames = _frames(view)
        held = cls._focus.get(view)
        if held is not None:
            canvas, index = held
            if canvas() is view.scene() and 0 <= index < len(frames) \
                    and frames[index].isVisible():
                return index
        index = focus_page(view)
        cls._note_focus(view, index)
        return index

    @classmethod
    def _note_focus(cls, view, index: Optional[int]) -> None:
        if index is None or view.scene() is None:
            cls._focus.pop(view, None)
        else:
            cls._focus[view] = (weakref.ref(view.scene()), index)

    # -- who follows ---------------------------------------------------------
    def _document_in(self, view):
        window = self.window
        if view is getattr(window, "view", None):
            return window.document
        for pane in getattr(window, "_panes", ()):
            if pane.view is view and pane.documents:
                return pane.documents[pane.active]["document"]
        return None

    def followers(self, view) -> list:
        """The views that follow *view*: the other view of the split, and
        the view of each other window showing its document with Sync on."""
        window = self.window
        if window is None or self.mode() == OFF:
            return []
        found = []
        panes = list(getattr(window, "_panes", ()))
        if len(panes) > 1 and any(pane.view is view for pane in panes):
            for pane in panes:
                if pane.view is not view and pane.view.scene() is not None:
                    found.append(Follower(window, pane.view,
                                          None if pane.view is window.view else pane))
        document = self._document_in(view)
        if document is not None:
            for other in list(type(window)._windows):
                try:
                    if (other is window or other.document is not document
                            or other.window_sync.currentIndex() == OFF
                            or other.view.scene() is None):
                        continue
                except RuntimeError:
                    continue                  # a window being taken down
                found.append(Follower(other, other.view))
        return found

    # -- links ---------------------------------------------------------------
    @classmethod
    def _forget_the_dead(cls) -> None:
        for key, (first, second, *_rest) in list(cls._links.items()):
            if first() is None or second() is None:
                del cls._links[key]

    @classmethod
    def link(cls, first, second) -> None:
        """Note how far apart *first* and *second* are now."""
        found = link_between(first, second)
        key = (id(first), id(second))
        cls._links.pop((id(second), id(first)), None)
        if found is None:
            cls._links.pop(key, None)
            return
        # held weakly: a link keeps no view and no canvas alive
        cls._links[key] = (weakref.ref(first), weakref.ref(second),
                           weakref.ref(first.scene()), weakref.ref(second.scene()), found)

    @classmethod
    def link_from(cls, source, follower) -> Optional[Link]:
        """The link that takes *source*'s place to *follower*'s."""
        cls._forget_the_dead()
        for key, onward in (((id(source), id(follower)), True),
                            ((id(follower), id(source)), False)):
            held = cls._links.get(key)
            if held is None:
                continue
            first, second, first_scene, second_scene, found = held
            scenes = (source.scene(), follower.scene()) if onward else \
                (follower.scene(), source.scene())
            if (first(), second()) != ((source, follower) if onward else (follower, source)) \
                    or scenes != (first_scene(), second_scene()):
                continue                       # another document since: stale
            return found if onward else found.reversed()
        # never linked (or since changed): linked as they are now
        cls.link(source, follower)
        held = cls._links.get((id(source), id(follower)))
        return held[-1] if held else None

    def relink(self) -> None:
        """Note how far apart every pair of views that may follow each other
        is now: after the sync is chosen, or a view shows another document."""
        window = self.window
        if window is None or getattr(window, "view", None) is None:
            return
        views = [pane.view for pane in getattr(window, "_panes", ())] or [window.view]
        for view in views:
            self._note_focus(view, focus_page(view))
            for follower in self._all_followers(view):
                self.link(view, follower.view)
                self._note_focus(follower.view, focus_page(follower.view))

    def _all_followers(self, view) -> list:
        """As followers(), whatever the sync is now."""
        window = self.window
        found = []
        panes = list(getattr(window, "_panes", ()))
        if len(panes) > 1:
            found += [Follower(window, pane.view) for pane in panes
                      if pane.view is not view and pane.view.scene() is not None]
        document = self._document_in(view)
        for other in list(type(window)._windows):
            try:
                if other is not window and document is not None \
                        and other.document is document and other.view.scene() is not None:
                    found.append(Follower(other, other.view))
            except RuntimeError:
                continue
        return found

    # -- carrying a move -----------------------------------------------------
    def moved(self, view) -> None:
        """*view* was zoomed or scrolled (by anything at all)."""
        if self._carrying or getattr(view, "_zooming", False) or view.scene() is None:
            return
        mode = self.mode()
        if mode == PAGE:
            self._page_moved(view)
            return
        if mode != DOCUMENT:
            return
        followers = self.followers(view)
        if not followers:
            return
        here = place_of(view)
        if here is None:
            return
        with self.quiet():
            for follower in followers:
                try:
                    self._follow(view, here, follower)
                except RuntimeError:
                    continue                   # a view being taken down

    def _page_moved(self, source) -> None:
        """Page sync: the other views take *source*'s zoom and its spot on
        its page in focus, each on its own page in focus."""
        was = self._page_in_focus(source)
        here = focus_page(source)
        if here is None or was is None:
            return
        # scrolled on across a page boundary: the others go on across theirs
        step = 0 if self._jumping else here - was
        self._note_focus(source, here)
        followers = self.followers(source)
        if not followers:
            return
        box = page_box(_frames(source)[here])
        middle = source.viewportTransform().inverted()[0].map(middle_of(source))
        offset = middle - box.topLeft()
        with self.quiet():
            for follower in followers:
                try:
                    self._take_spot(source, offset, box, step, follower)
                except RuntimeError:
                    continue

    def _take_spot(self, source, offset: QPointF, box: QRectF, step: int,
                   follower: Follower) -> None:
        view = follower.view
        frames = _frames(view)
        if not frames:
            return
        index = self._page_in_focus(view)
        index = max(0, min((index if index is not None else 0) + step, len(frames) - 1))
        if view.scene() is source.scene() and one_page_at_a_time(source):
            index = focus_page(source)          # one canvas, one spread shown: its page
        follower.bring_page_on(index)
        view.set_zoom(source.zoom())
        there = page_box(frames[index])
        view.bring_to(QPointF(there.left() + same_spot(offset.x(), box.width(), there.width()),
                              there.top() + same_spot(offset.y(), box.height(), there.height())),
                      middle_of(view))
        self._note_focus(view, index)

    def _follow(self, source, here: Place, follower: Follower) -> None:
        link = self.link_from(source, follower.view)
        if link is None:
            return
        there = reachable(follower.view, link.onward(here))
        if follower.view.scene() is source.scene() and one_page_at_a_time(source):
            # one canvas showing one spread: both views are on its page
            there = Place(here.page, there.across, there.down, there.zoom)
        follower.bring_page_on(there.page)
        put(follower.view, there)

    def paged(self, view, index: int) -> None:
        """*view* went to (or was scrolled onto) page *index*."""
        if self._carrying or view.scene() is None:
            return
        if self.mode() in (PAGE, DOCUMENT):
            self.moved(view)
