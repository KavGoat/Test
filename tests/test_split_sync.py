"""Split View's Window Sync, driven by real input and measured exactly.

The user, 2026-10-19: "Page sync and document sync need to be more robust;
also had issues in Split View where zooming on one (without any sync) moved
the other a little bit." Revu's three choices (calcforge/ui/viewsync.py):

- Sync off: nothing done in one view moves the other, by even a pixel;
- Page sync (the user's correction, 2026-10-19: "only zoom and positioning,
  it doesn't care what page"): each view stays on its own page and takes
  the other's zoom and its spot on its page in focus — the same points
  from the page's top left as it lies on screen;
- Document sync: scroll, zoom and page changes in one are repeated in the
  other by the same relative amount, across different documents too.

Each is tried with two different documents (pages of other sizes, a turned
page, other page counts) and with one document in both views.
"""
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.ui import viewsync
from tests.test_canvas import wheel

#: how close two canvas points must be (points of the page)
EXACT = 0.01


def _settle(times=4):
    for _ in range(times):
        QApplication.processEvents()


def _pdf(path, sizes, rotate=()):
    """A PDF with a page of each of *sizes* (points); pages listed in
    *rotate* are turned a quarter."""
    import fitz
    doc = fitz.open()
    for number, (width, height) in enumerate(sizes):
        page = doc.new_page(width=width, height=height)
        page.insert_text((40, 60), f"{path.stem} page {number + 1}")
        if number in rotate:
            page.set_rotation(90)
    doc.save(str(path))
    doc.close()
    return path


A4 = (595, 842)
A3_WIDE = (1191, 842)
SMALL = (420, 297)


def _open_split(window, tmp_path, same=False):
    """a.pdf (five pages, one wide, one turned) and b.pdf (three smaller
    pages) side by side — or b.pdf in both views when *same*. Returns the
    pane showing a.pdf and the one showing b.pdf (with *same*, the first
    view and the second)."""
    a = _pdf(tmp_path / "a.pdf", [A4, A4, A3_WIDE, A4, A4], rotate=(3,))
    b = _pdf(tmp_path / "b.pdf", [SMALL, SMALL, A4])
    window.show()
    window.activateWindow()
    QTest.qWaitForWindowActive(window)
    window.open_from_command_line(str(a))
    window.open_in_new_tab()
    window.open_from_command_line(str(b))
    _settle()
    if same:
        window.act_split_view.trigger()               # b.pdf in both views
    else:
        window.split_document(0)                      # a.pdf beside b.pdf
    _settle()
    assert window.is_split
    left, right = window._panes
    for pane in (left, right):
        pane.view.finish_scrolling()
    if not same and _document_of(window, left).path.endswith("b.pdf"):
        left, right = right, left
    return left, right


def _document_of(window, pane):
    if pane is window._active_pane:
        return window.document
    return pane.documents[pane.active]["document"]


def _centre(view) -> QPointF:
    """The canvas point in the middle of *view*, exactly."""
    return view.viewportTransform().inverted()[0].map(QPointF(view.viewport().rect().center()))


def _where(view):
    return _centre(view), view.zoom()


def _unmoved(view, before, tolerance=EXACT):
    centre, zoom = _where(view)
    assert zoom == pytest.approx(before[1], abs=1e-9), "the other view's zoom changed"
    assert abs(centre.x() - before[0].x()) <= tolerance and \
        abs(centre.y() - before[0].y()) <= tolerance, \
        f"the other view moved: {before[0]} -> {centre}"


def _set_sync(window, mode):
    window.window_sync.setCurrentIndex(mode)
    _settle()


def _in_hand(window, pane):
    """Click the pane's canvas, as a person does, to make it the one in hand."""
    QTest.mouseClick(pane.view.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(12, 12))
    _settle()
    assert window.view is pane.view


def _page(window, pane) -> int:
    return window.current_index if pane.view is window.view else pane.view._shown_page


def _place(view):
    return viewsync.place_of(view)


# -- Sync off: the other view never moves --------------------------------------

@pytest.mark.parametrize("same", [False, True], ids=["two documents", "one document"])
def test_sync_off_nothing_done_in_one_view_moves_the_other(window, tmp_path, same):
    left, right = _open_split(window, tmp_path, same)
    _set_sync(window, viewsync.OFF)
    _in_hand(window, right)
    still = _where(left.view)
    view = right.view
    rect = view.viewport().rect()
    # the wheel zooms at the pointer, here and there, in and out
    for x, y, notches in ((20, 20, 120), (rect.width() - 30, rect.height() - 40, 240),
                          (rect.width() // 3, rect.height() // 2, -360), (60, 300, 120)):
        wheel(view, notches, at=QPointF(x, y))
        _unmoved(left.view, still)
    # Zoom In and Out, Fit Page, Fit Width, Actual Size, Zoom to Selection
    for action in (window.act_zoom_in, window.act_zoom_in, window.act_zoom_out,
                   window.act_fit_page, window.act_fit_width, window.act_actual_size):
        action.trigger()
        _settle(1)
        _unmoved(left.view, still)
    # scrolling: Ctrl+wheel, Shift+wheel sideways, a trackpad's pixels
    wheel(view, -240, Qt.ControlModifier)
    wheel(view, -120, Qt.ShiftModifier)
    wheel(view, -90, pixels=True)
    _unmoved(left.view, still)
    # pages: Page Down, Ctrl+Right, End, Home, the page box
    for key, modifiers in ((Qt.Key_PageDown, Qt.NoModifier), (Qt.Key_Right, Qt.ControlModifier),
                           (Qt.Key_End, Qt.NoModifier), (Qt.Key_Home, Qt.NoModifier)):
        QTest.keyClick(view, key, modifiers)
        _settle(1)
        _unmoved(left.view, still)
    window.page_spin.setFocus()
    window.page_spin.selectAll()
    QTest.keyClicks(window.page_spin, "2")
    QTest.keyClick(window.page_spin, Qt.Key_Return)
    _settle()
    if not same:
        _unmoved(left.view, still)


def test_sync_off_a_view_at_the_edge_of_its_desk_is_not_pulled_in(window, tmp_path):
    """The bug as it was: the desk round the pages belonged to the canvas
    both views shared, sized by whichever view zoomed last. Zoomed out and
    scrolled to its top left corner, one view was dragged 185 pt across and
    350 pt down when the other zoomed in and the shared desk shrank."""
    left, right = _open_split(window, tmp_path, same=True)
    _set_sync(window, viewsync.OFF)
    _in_hand(window, right)
    for _ in range(4):
        wheel(left.view, -120, at=QPointF(5, 5))
    for _ in range(30):
        wheel(left.view, 240, Qt.ControlModifier)       # to the top ...
        wheel(left.view, 240, Qt.ShiftModifier)         # ... left corner
    assert left.view.verticalScrollBar().value() == left.view.verticalScrollBar().minimum()
    still = _where(left.view)
    for _ in range(6):
        wheel(right.view, 120, at=QPointF(150, 150))
        _unmoved(left.view, still)
    window.act_zoom_in.trigger()
    _unmoved(left.view, still)


def test_sync_off_the_wheel_over_the_view_not_in_hand_moves_only_it(window, tmp_path):
    left, right = _open_split(window, tmp_path, same=True)
    _set_sync(window, viewsync.OFF)
    _in_hand(window, right)
    still = _where(right.view)
    for notches in (120, 120, -240, 360):
        wheel(left.view, notches, at=QPointF(40, 50))
        wheel(left.view, -120, Qt.ControlModifier)
        _unmoved(right.view, still)
    assert window.view is right.view, "the wheel does not change the view in hand"


@pytest.mark.parametrize("same", [False, True], ids=["two documents", "one document"])
def test_sync_off_resizing_the_split_leaves_the_other_view_where_it_was(window, tmp_path, same):
    """Dragging the divider resizes both views; each keeps the middle of
    what it shows (to the pixel) and its zoom; zooming one afterwards still
    moves only it."""
    left, right = _open_split(window, tmp_path, same)
    _set_sync(window, viewsync.OFF)
    wheel(right.view, 240, at=QPointF(50, 50))
    wheel(left.view, -120, at=QPointF(80, 120))
    sizes = window.view_split.sizes()
    for share in (0.35, 0.6, 0.5):
        before = _where(left.view)
        total = sum(sizes)
        window.view_split.setSizes([int(total * share), total - int(total * share)])
        _settle()
        _unmoved(left.view, before, tolerance=0.5 / left.view.zoom())
    _in_hand(window, right)
    still = _where(left.view)
    wheel(right.view, 120, at=QPointF(10, 10))
    window.act_fit_width.trigger()
    _unmoved(left.view, still)


def test_sync_off_clicking_into_the_other_view_moves_neither(window, tmp_path):
    """A click makes a view the one in hand, and the formula bar goes with it
    (both on spreadsheet pages here): neither view's pages move on screen."""
    left, right = _open_split(window, tmp_path)
    _set_sync(window, viewsync.OFF)
    for pane in (left, right):
        _in_hand(window, pane)
        window.insert_sheet_page(0)
        _settle(6)
        # scrolled onto its page (gone to, it opens alone: the workbook view),
        # the desk at the left where the clicks below land (a click on its
        # cells would open the workbook view)
        pane.view.go_to_page_top(1)
        bar = pane.view.horizontalScrollBar()
        bar.setValue(bar.minimum())
        _settle()
    assert window.formula_bar.isVisible()
    for pane in (left, right, left, right):
        corners = {}
        for view in (left.view, right.view):
            corners[view] = (view.viewport().mapToGlobal(QPoint(0, 0)),
                             view.viewportTransform().inverted()[0].map(QPointF(0, 0)))
        _in_hand(window, pane)
        assert window.formula_bar.isVisible()
        assert pane.view.parentWidget().isAncestorOf(window.formula_bar) or \
            pane.widget.isAncestorOf(window.formula_bar)
        for view, (corner, point) in corners.items():
            now = view.viewport().mapToGlobal(QPoint(0, 0))
            shown_at = view.viewportTransform().map(point) + QPointF(now - corner)
            assert abs(shown_at.x()) <= 0.5 and abs(shown_at.y()) <= 0.5, \
                "a view's pages moved on the screen when the other was clicked"


# -- Page sync -----------------------------------------------------------------

def _focus(view):
    return viewsync.ViewSync._page_in_focus(view)


def _spot(view, index=None):
    """The middle of *view* in points from the top left of its page in
    focus (as the page lies on screen), and that page's box."""
    index = _focus(view) if index is None else index
    box = viewsync.page_box(view.scene().frames[index])
    return _centre(view) - box.topLeft(), box


def _same_spot(source, follower):
    """The follower is at the source's zoom, at the same spot of its own
    page in focus — to the pixel, except along a side where it has run out
    of room to scroll."""
    assert follower.zoom() == pytest.approx(source.zoom(), rel=1e-9), "not the same zoom"
    offset, box = _spot(source, viewsync.focus_page(source))
    there, other = _spot(follower)
    wanted = QPointF(viewsync.same_spot(offset.x(), box.width(), other.width()),
                     viewsync.same_spot(offset.y(), box.height(), other.height()))
    pixel = 0.5 / follower.zoom() + 1e-6
    for axis, bar in (("x", follower.horizontalScrollBar()), ("y", follower.verticalScrollBar())):
        if bar.value() in (bar.minimum(), bar.maximum()):
            continue                            # out of room that way
        assert abs(getattr(there, axis)() - getattr(wanted, axis)()) <= pixel, \
            f"not the same spot along {axis}: {there} != {wanted}"


def _onto_page(window, pane, index):
    """With Sync off, put *pane*'s view on page *index* (it stays in hand)."""
    _set_sync(window, viewsync.OFF)
    _in_hand(window, pane)
    window.go_to_page(index)
    _settle()


@pytest.mark.parametrize("same", [False, True], ids=["two documents", "one document"])
def test_page_sync_takes_the_zoom_and_spot_on_each_views_own_page(window, tmp_path, same):
    left, right = _open_split(window, tmp_path, same)
    _onto_page(window, right, 1)
    _in_hand(window, left)
    _set_sync(window, viewsync.PAGE)                  # chosen: in step at once
    _same_spot(left.view, right.view)
    view = left.view
    rect = view.viewport().rect()
    for x, y, notches in ((30, 40, 120), (rect.width() - 20, rect.height() - 30, 240),
                          (rect.width() // 2, 60, -120)):
        wheel(view, notches, at=QPointF(x, y))
        _same_spot(view, right.view)
    for action in (window.act_zoom_in, window.act_zoom_out, window.act_fit_width):
        action.trigger()
        _settle(1)
        _same_spot(view, right.view)
    for modifiers, notches in ((Qt.ShiftModifier, -120), (Qt.ControlModifier, -120),
                               (Qt.ControlModifier, 120)):
        wheel(view, notches, modifiers)
        _same_spot(view, right.view)
    assert _focus(right.view) == 1, "the other view stays on its own page"
    # and the other way, by the wheel over the view not in hand
    wheel(right.view, 240, at=QPointF(60, 70))
    _same_spot(right.view, left.view)
    assert window.view is left.view


def test_page_sync_going_to_a_page_leaves_the_other_on_its_page(window, tmp_path):
    left, right = _open_split(window, tmp_path)       # a.pdf (5 pages) | b.pdf (3)
    _onto_page(window, right, 1)
    _in_hand(window, left)
    _set_sync(window, viewsync.PAGE)
    window.show_panel("dock_pages", True)
    _settle()
    strip = window.pages_panel.list
    point = strip.visualItemRect(strip.item(2)).center()
    QTest.mouseClick(strip.viewport(), Qt.LeftButton, Qt.NoModifier, point)   # a thumbnail
    _settle()
    assert window.current_index == 2
    assert _focus(right.view) == 1
    _same_spot(left.view, right.view)
    window.page_spin.setFocus()
    window.page_spin.selectAll()
    QTest.keyClicks(window.page_spin, "2")                                      # the page box
    QTest.keyClick(window.page_spin, Qt.Key_Return)
    _settle()
    assert window.current_index == 1 and _focus(right.view) == 1
    for key, modifiers, page in ((Qt.Key_Right, Qt.ControlModifier, 2),
                                 (Qt.Key_End, Qt.NoModifier, 4),
                                 (Qt.Key_Home, Qt.NoModifier, 0)):
        QTest.keyClick(window.view, key, modifiers)
        _settle()
        assert window.current_index == page
        assert _focus(right.view) == 1, "going to a page leaves the other on its page"
        _same_spot(left.view, right.view)


def test_page_sync_by_bookmark_find_and_link_leaves_the_other_on_its_page(window, tmp_path):
    left, right = _open_split(window, tmp_path)
    _onto_page(window, right, 2)
    _in_hand(window, left)
    _set_sync(window, viewsync.PAGE)
    window.go_to_bookmark(3, 100.0)                   # a bookmark
    assert window.current_index == 3 and _focus(right.view) == 2
    _same_spot(left.view, right.view)
    panel = window.search_panel                       # a Find result
    panel.query.setText("a page 2")
    QTest.keyClick(panel.query, Qt.Key_Return)
    _settle()
    panel.show_hit(panel.results.topLevelItem(0))
    _settle()
    assert window.current_index == 1 and _focus(right.view) == 2
    _same_spot(left.view, right.view)
    from calcforge.items.link import PAGE, LinkItem   # a link, double-clicked
    from PySide6.QtCore import QRectF
    window.go_to_page(0)
    link = LinkItem(QRectF(0, 0, 120, 30))
    link.kind, link.target_page = PAGE, 4
    window.view.frame().add_markup(link, QPointF(100, 100))
    _settle()
    centre = link.sceneBoundingRect().center()
    window.view.centerOn(centre)
    _settle()
    QTest.mouseDClick(window.view.viewport(), Qt.LeftButton, Qt.NoModifier,
                      window.view.mapFromScene(centre))
    _settle()
    assert window.current_index == 4 and _focus(right.view) == 2
    _same_spot(left.view, right.view)


def test_page_sync_a_smaller_or_turned_page_lines_up_in_points(window, tmp_path):
    """A wide page beside a small one: the same points in, stopping at the
    small page's edge; on a turned page, points as it lies on screen."""
    left, right = _open_split(window, tmp_path)       # a.pdf | b.pdf
    _onto_page(window, right, 0)                      # b: 420 x 297
    _onto_page(window, left, 2)                       # a: 1191 x 842, wide
    _set_sync(window, viewsync.PAGE)
    for _ in range(3):
        wheel(left.view, 120, at=QPointF(left.view.viewport().rect().center()))
    box = viewsync.page_box(left.view.scene().frames[2])
    middle = QPointF(left.view.viewport().rect().center())
    for spot, expected in ((QPointF(100, 80), QPointF(100, 80)),           # on both pages
                           (QPointF(900, 600), QPointF(420, 297)),         # past b's edge
                           (QPointF(-10, 30), QPointF(-10, 30))):          # the desk before
        left.view.bring_to(box.topLeft() + spot, middle)
        _settle(1)
        _same_spot(left.view, right.view)
        there, _box = _spot(right.view)
        assert abs(there.x() - expected.x()) <= 1.0 / right.view.zoom()
        assert abs(there.y() - expected.y()) <= 1.0 / right.view.zoom()
    # page 4 of a.pdf is turned: it lies wider than tall, and lines up as it lies
    window.go_to_page(3)
    turned = viewsync.page_box(left.view.scene().frames[3])
    assert turned.width() > turned.height()
    left.view.bring_to(turned.topLeft() + QPointF(150, 120), middle)
    _settle(1)
    _same_spot(left.view, right.view)
    assert _focus(right.view) == 0


def test_page_sync_scrolling_on_across_a_page_boundary_carries_the_other(window, tmp_path):
    left, right = _open_split(window, tmp_path)       # a.pdf (5) | b.pdf (3)
    _in_hand(window, left)
    window.go_to_page(0)
    _set_sync(window, viewsync.PAGE)
    assert _focus(right.view) == 0
    seen = set()
    for _ in range(400):
        wheel(left.view, -240, Qt.ControlModifier)
        seen.add((viewsync.focus_page(left.view), _focus(right.view)))
        _same_spot(left.view, right.view)
        if viewsync.focus_page(left.view) == 4:
            break
    assert (1, 1) in seen and (2, 2) in seen, "the other went on across its own pages"
    assert _focus(right.view) == 2, "b.pdf has three pages: it stays on its last"


def test_page_sync_does_not_echo_back(window, tmp_path):
    """Going to a page moves the other view once; the view gone from stays
    exactly where going to the page put it, and nothing goes back and forth."""
    left, right = _open_split(window, tmp_path, same=True)
    _in_hand(window, left)
    _set_sync(window, viewsync.PAGE)
    window.act_zoom_out.trigger()
    window.act_zoom_out.trigger()                     # zoomed out: several pages in sight
    _settle()
    calls = []
    original = window.go_to_page

    def counted(index):
        calls.append(index)
        original(index)
    window.go_to_page = counted
    try:
        window.go_to_page(2)
        here, there = _where(left.view), _where(right.view)
        _settle(6)
        _unmoved(left.view, here)
        _unmoved(right.view, there)
        assert calls == [2], f"went to pages {calls}: the move came back"
    finally:
        del window.go_to_page


def test_page_sync_survives_mode_changes_split_off_and_on_and_tab_switches(window, tmp_path):
    left, right = _open_split(window, tmp_path)
    _in_hand(window, left)
    _set_sync(window, viewsync.PAGE)
    wheel(left.view, 120, at=QPointF(40, 40))
    _same_spot(left.view, right.view)
    _set_sync(window, viewsync.OFF)
    still = _where(right.view)
    wheel(left.view, 240, at=QPointF(40, 40))
    _unmoved(right.view, still)
    _set_sync(window, viewsync.PAGE)
    _same_spot(left.view, right.view)
    # the right view shows its other document now
    _in_hand(window, right)
    right.tabs.setCurrentIndex(1 - right.tabs.currentIndex())
    _settle()
    wheel(right.view, -120, at=QPointF(70, 50))
    _same_spot(right.view, left.view)
    # split off and on again
    window.act_split_view.trigger()
    _settle()
    assert not window.is_split
    window.act_split_view.trigger()
    _settle()
    _set_sync(window, viewsync.PAGE)
    first, second = window._panes
    other = first if window.view is second.view else second
    wheel(window.view, 120, at=QPointF(30, 30))
    _same_spot(window.view, other.view)


# -- Document sync ------------------------------------------------------------

def _steps_together(source, follower, before_source, before_follower, link=None):
    """The follower moved with the source: its zoom by the same factor, and
    it is where the link puts it — the source's place plus the difference
    noted when they were linked — to the pixel, except along a side where
    it has run out of room to scroll (it has fewer pages, or a smaller page
    with less desk round it)."""
    a0, b0 = before_source, before_follower
    a1 = _place(source)
    assert follower.zoom() / b0.zoom == pytest.approx(a1.zoom / a0.zoom, rel=1e-9), \
        "the zoom changed by another factor"
    link = link or viewsync.ViewSync.link_from(source, follower)
    wanted = viewsync.reachable(follower, link.onward(a1))
    box = _box(follower, wanted.page)
    point = QPointF(box.left() + wanted.across * box.width(), box.top() + wanted.down * box.height())
    centre = _centre(follower)
    pixel = 0.5 / follower.zoom() + 1e-6
    for axis, bar in (("x", follower.horizontalScrollBar()), ("y", follower.verticalScrollBar())):
        if bar.value() in (bar.minimum(), bar.maximum()):
            continue                           # out of room that way
        assert abs(getattr(centre, axis)() - getattr(point, axis)()) <= pixel, \
            f"the follower is out of step along {axis}: {centre} != {point}"


def _box(view, index):
    return viewsync.page_box(view.scene().frames[index])


@pytest.mark.parametrize("same", [False, True], ids=["two documents", "one document"])
def test_document_sync_zoom_and_scroll_are_repeated_by_the_same_amount(window, tmp_path, same):
    left, right = _open_split(window, tmp_path, same)
    _in_hand(window, left)
    wheel(right.view, 120, at=QPointF(40, 40))       # apart before the link
    _set_sync(window, viewsync.DOCUMENT)
    linked = viewsync.link_between(left.view, right.view)
    rect = left.view.viewport().rect()
    for x, y, notches in ((30, 40, 120), (rect.width() - 20, rect.height() - 30, 240),
                          (rect.width() // 2, 60, -120)):
        a0, b0 = _place(left.view), _place(right.view)
        wheel(left.view, notches, at=QPointF(x, y))
        _steps_together(left.view, right.view, a0, b0)
    for modifiers, notches in ((Qt.ControlModifier, -240), (Qt.ShiftModifier, -120),
                               (Qt.ControlModifier, 120)):
        a0, b0 = _place(left.view), _place(right.view)
        wheel(left.view, notches, modifiers)
        _steps_together(left.view, right.view, a0, b0)
    # the link held all the way: the views are as far apart as they began
    now = viewsync.link_between(left.view, right.view)
    assert now.zoom == pytest.approx(linked.zoom, rel=1e-9)
    assert now.pages == linked.pages


def test_document_sync_works_from_either_view_and_with_commands(window, tmp_path):
    left, right = _open_split(window, tmp_path)
    _in_hand(window, left)
    _set_sync(window, viewsync.DOCUMENT)
    linked = viewsync.link_between(left.view, right.view)
    # from the view not in hand, by the wheel
    a0, b0 = _place(right.view), _place(left.view)
    wheel(right.view, 240, at=QPointF(70, 90))
    _steps_together(right.view, left.view, a0, b0)
    # from the one in hand, by Zoom In / Out and Fit Width
    for action in (window.act_zoom_in, window.act_zoom_out, window.act_fit_width):
        a0, b0 = _place(left.view), _place(right.view)
        action.trigger()
        _settle(1)
        _steps_together(left.view, right.view, a0, b0)
    assert viewsync.link_between(left.view, right.view).zoom == pytest.approx(linked.zoom)


def test_document_sync_pages_follow_and_clamp_at_the_others_last_page(window, tmp_path):
    left, right = _open_split(window, tmp_path)       # a.pdf (5) | b.pdf (3)
    _in_hand(window, left)
    _set_sync(window, viewsync.DOCUMENT)
    window.go_to_page(2)                              # a wide page
    assert _page(window, right) == 2
    window.go_to_page(3)                              # a turned page; b has none
    place = _place(right.view)
    assert place.page == 2 and place.down >= 1.0 - EXACT, \
        "beyond its last page the other stays at the foot of its last page"
    window.go_to_page(1)
    assert _page(window, right) == 1
    a, b = _place(left.view), _place(right.view)
    link = viewsync.link_between(left.view, right.view)
    assert link.pages == 0 and b.page == a.page


def test_document_sync_a_notch_landing_at_once_moves_both_at_once(window, tmp_path):
    """Out of the box a notch lands at once (as Revu): the other view is in
    step as soon as it has been handled, and nothing goes back and forth."""
    left, right = _open_split(window, tmp_path, same=True)
    _in_hand(window, left)
    _set_sync(window, viewsync.DOCUMENT)
    from PySide6.QtGui import QWheelEvent
    view = left.view
    link = viewsync.link_between(left.view, right.view)
    start = (_place(left.view), _place(right.view), left.view.zoom())
    at = QPointF(100, 100)
    QApplication.sendEvent(view.viewport(), QWheelEvent(
        at, view.viewport().mapToGlobal(at.toPoint()), QPoint(0, 0), QPoint(0, 240),
        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
    assert left.view.zoom() == pytest.approx(start[2] * 1.0015 ** 240, rel=1e-9)
    _steps_together(left.view, right.view, start[0], start[1], link)
    landed = (_where(left.view), _where(right.view))
    QTest.qWait(60)
    _settle(6)
    _unmoved(left.view, landed[0])
    _unmoved(right.view, landed[1])


def test_document_sync_glides_stay_in_step(window, tmp_path):
    """With Smooth zoom and scroll on, a notch glides over several frames;
    the other view takes every step."""
    from calcforge.ui import preferences
    preferences.current().smooth_wheel = True
    left, right = _open_split(window, tmp_path, same=True)
    _in_hand(window, left)
    _set_sync(window, viewsync.DOCUMENT)
    from PySide6.QtGui import QWheelEvent
    view = left.view
    link = viewsync.link_between(left.view, right.view)
    start = (_place(left.view), _place(right.view))
    at = QPointF(100, 100)
    QApplication.sendEvent(view.viewport(), QWheelEvent(
        at, view.viewport().mapToGlobal(at.toPoint()), QPoint(0, 0), QPoint(0, 240),
        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
    seen = 0
    for _ in range(40):
        a0, b0 = start
        QTest.qWait(8)
        _steps_together(left.view, right.view, a0, b0, link)
        seen += 1
        if not view.glide.timer.isActive():
            break
    view.finish_scrolling()
    _steps_together(left.view, right.view, *start, link)
    assert seen > 1, "the zoom glided over several frames"
    # and once it has landed, nothing goes back and forth
    landed = (_where(left.view), _where(right.view))
    QTest.qWait(60)
    _settle(6)
    _unmoved(left.view, landed[0])
    _unmoved(right.view, landed[1])


def test_document_sync_choosing_it_moves_nothing_and_off_unlinks(window, tmp_path):
    left, right = _open_split(window, tmp_path)
    wheel(left.view, 120, at=QPointF(10, 10))
    before = (_where(left.view), _where(right.view))
    _set_sync(window, viewsync.DOCUMENT)
    _unmoved(left.view, before[0])
    _unmoved(right.view, before[1])
    _set_sync(window, viewsync.OFF)
    still = _where(right.view)
    wheel(left.view, 240, at=QPointF(10, 10))
    _unmoved(right.view, still)


def test_document_sync_single_page_mode_and_a_tab_switch(window, tmp_path):
    left, right = _open_split(window, tmp_path)
    _in_hand(window, left)
    for pane in (left, right):
        pane.view.scene().set_page_mode("single", 0)
    _set_sync(window, viewsync.DOCUMENT)
    window.go_to_page(1)
    assert right.view.scene().frames[1].isVisible(), "the other shows the same page"
    assert _page(window, right) == 1
    a0, b0 = _place(left.view), _place(right.view)
    wheel(left.view, 120, at=QPointF(50, 50))
    _steps_together(left.view, right.view, a0, b0)
    # a tab switch in the other view: linked anew, where it is
    _in_hand(window, right)
    if right.tabs.count() > 1:
        right.tabs.setCurrentIndex(1 - right.tabs.currentIndex())
        _settle()
    _in_hand(window, left)
    a0, b0 = _place(left.view), _place(right.view)
    wheel(left.view, -120, at=QPointF(50, 50))
    _steps_together(left.view, right.view, a0, b0)
