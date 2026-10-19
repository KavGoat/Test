"""Split View's Window Sync, driven by real input and measured exactly.

The user, 2026-10-19: "Page sync and document sync need to be more robust;
also had issues in Split View where zooming on one (without any sync) moved
the other a little bit." Revu's three choices (calcforge/ui/viewsync.py):

- Sync off: nothing done in one view moves the other, by even a pixel;
- Page sync: going to a page in one goes to the same page number in the
  other (its last page when it has fewer); zoom and scroll are each its own;
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
        window.go_to_page(1)
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

def test_page_sync_follows_the_page_by_thumbnails_page_box_and_keys(window, tmp_path):
    left, right = _open_split(window, tmp_path)       # a.pdf (5 pages) | b.pdf (3)
    _in_hand(window, left)
    _set_sync(window, viewsync.PAGE)
    assert window.document.path.endswith("a.pdf")
    assert _document_of(window, right).path.endswith("b.pdf")
    other = right.view
    zoom = other.zoom()
    # a thumbnail clicked
    window.show_panel("dock_pages", True)
    _settle()
    strip = window.pages_panel.list
    point = strip.visualItemRect(strip.item(1)).center()
    QTest.mouseClick(strip.viewport(), Qt.LeftButton, Qt.NoModifier, point)
    _settle()
    assert window.current_index == 1 and _page(window, right) == 1
    # the page box
    window.page_spin.setFocus()
    window.page_spin.selectAll()
    QTest.keyClicks(window.page_spin, "3")
    QTest.keyClick(window.page_spin, Qt.Key_Return)
    _settle()
    assert window.current_index == 2 and _page(window, right) == 2
    # Page Up, then past the other's last page: it stays on its last
    QTest.keyClick(window.view, Qt.Key_Right, Qt.ControlModifier)
    _settle()
    assert window.current_index == 3 and _page(window, right) == 2
    QTest.keyClick(window.view, Qt.Key_End)
    _settle()
    assert window.current_index == 4 and _page(window, right) == 2
    QTest.keyClick(window.view, Qt.Key_Home)
    _settle()
    assert window.current_index == 0 and _page(window, right) == 0
    assert other.zoom() == pytest.approx(zoom), "Page sync leaves the zoom alone"


def test_page_sync_the_zoom_and_scroll_stay_each_views_own(window, tmp_path):
    left, right = _open_split(window, tmp_path)
    _in_hand(window, left)
    _set_sync(window, viewsync.PAGE)
    still = _where(right.view)
    wheel(left.view, 240, at=QPointF(60, 60))
    window.act_zoom_out.trigger()
    wheel(left.view, -60, Qt.ShiftModifier)
    _unmoved(right.view, still)


def test_page_sync_scrolling_across_a_page_boundary_turns_the_other(window, tmp_path):
    left, right = _open_split(window, tmp_path)
    _in_hand(window, left)
    _set_sync(window, viewsync.PAGE)
    for _ in range(80):
        wheel(left.view, -240, Qt.ControlModifier)
        if window.current_index >= 1:
            break
    assert window.current_index == 1
    assert _page(window, right) == 1
    # and from the view not in hand: its scroll turns the one in hand
    _in_hand(window, left)
    for _ in range(80):
        wheel(right.view, -240, Qt.ControlModifier)
        if right.view._shown_page >= 2:
            break
    _settle()
    assert right.view._shown_page == 2
    assert window.current_index == 2


def test_page_sync_does_not_echo_back(window, tmp_path):
    """Going to a page moves the other view once; the view gone from stays
    exactly where going to the page put it."""
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
        here = _where(left.view)
        _settle(6)
        _unmoved(left.view, here)
        assert calls == [2], f"went to pages {calls}: the move came back"
        assert _page(window, right) == 2
    finally:
        del window.go_to_page


def test_page_sync_by_bookmark_find_and_link(window, tmp_path):
    left, right = _open_split(window, tmp_path)
    _in_hand(window, left)
    _set_sync(window, viewsync.PAGE)
    # a bookmark
    window.go_to_bookmark(2, 100.0)
    assert window.current_index == 2 and _page(window, right) == 2
    # a Find result: the page it is on, the words brought into view
    panel = window.search_panel
    panel.query.setText("a page 2")
    QTest.keyClick(panel.query, Qt.Key_Return)
    _settle()
    assert panel.results.topLevelItemCount() >= 1
    panel.show_hit(panel.results.topLevelItem(0))
    _settle()
    assert window.current_index == 1 and _page(window, right) == 1
    # a link on the page, double-clicked
    from calcforge.items.link import PAGE, LinkItem
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
    assert window.current_index == 4
    assert _page(window, right) == 2, "b.pdf has three pages: it stays on its last"


def test_page_sync_survives_mode_changes_split_off_and_on_and_tab_switches(window, tmp_path):
    left, right = _open_split(window, tmp_path)
    _in_hand(window, left)
    _set_sync(window, viewsync.PAGE)
    window.go_to_page(1)
    assert _page(window, right) == 1
    _set_sync(window, viewsync.OFF)
    window.go_to_page(3)
    assert _page(window, right) == 1, "Sync off: the other stays"
    _set_sync(window, viewsync.PAGE)
    window.go_to_page(0)
    assert _page(window, right) == 0
    # the right view shows another document now (its other tab)
    _in_hand(window, right)
    right.tabs.setCurrentIndex(0 if right.tabs.currentIndex() else 1) \
        if right.tabs.count() > 1 else None
    _settle()
    window.go_to_page(2)
    assert _page(window, left) == 2
    # split off and on again
    window.act_split_view.trigger()
    _settle()
    assert not window.is_split
    window.act_split_view.trigger()
    _settle()
    left, right = window._panes
    _set_sync(window, viewsync.PAGE)
    window.go_to_page(1)
    other = left if window.view is right.view else right
    assert _page(window, other) == 1


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


def test_document_sync_glides_stay_in_step(window, tmp_path):
    """A notch glides over several frames; the other view takes every step."""
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
