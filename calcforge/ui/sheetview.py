"""The workbook view: a sheet shown alone, filling the canvas, as Excel shows
it (the user, 2026-10-22: "Don't let me scroll from sheet to sheet: like
Excel, when I click a workbook it opens a [spreadsheet] with tabs at the
bottom" — "Not full window, fits the document panel completely").

Going to a workbook — its entry in Thumbnails, one of its pages (a click on
a cell, the page box), a sheet tab — shows the sheet alone: an endless grid
from A1 that scrolls within that sheet only, with its row and column
headings, the tab strip at the bottom to change sheet and a × at its end to
go back to the page you came from. No page edges and no other pages: the
sheet's pages sit edge to edge on the canvas, far to the left of every other page
(DocumentScene._lay_out_the_sheet), the canvas is only its grid, and the
grid grows down and to the right as the window is scrolled or zoomed out
(``scene.sheet_extent``). Where its pages fall is shown as Excel's Normal
view shows it, with thin dashed lines (items/sheetpage.py).

The pages are still the document's pages — Thumbnails, Print, Export and the
page numbers all go on as before — this is only how the sheet is shown and
edited. Its pages in the page view are its Page Layout view; Print's preview
is its print preview. Markups on its pages are shown where they are over the
cells, and can be picked and edited: they belong to the cells under them
(they move with them), so hiding them would leave cells to be typed into
blind under a cloud or a note.

Each workbook keeps its own zoom (Ctrl+wheel zooms the grid) and each sheet
where it was scrolled to and its active cell. Leaving: any other page in
Thumbnails or the page box, Ctrl+Page Up / Down past the first or last
sheet (between sheets they change sheet, as in Excel), or the ×.

The view is the canvas's (the document's), so both views of a document in
Split View show it.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer


def run_shown(scene) -> Optional[str]:
    """The sheet (run id) shown alone on *scene*, or None for the pages."""
    return getattr(scene, "sheet_view", None) if scene is not None else None


def is_on(window) -> bool:
    return run_shown(getattr(window, "scene", None)) is not None


def _item(window, uid: Optional[str]):
    from .sheetpages import run_items
    if uid is None or window.scene is None:
        return None
    return next((item for item in run_items(window.scene) if item.uid == uid
                 and item.sheet is not None), None)


def _section_key(window, uid: str) -> str:
    from .sheetpages import sections
    for section in sections(window.document):
        if uid in section.runs:
            return section.key
    return uid


def _first_page(window, uid: str) -> int:
    from .sheetpages import run_pages
    pages = run_pages(window.document, uid)
    return pages[0] if pages else 0


def _corner(view) -> QPointF:
    """The canvas point at the window's top left."""
    return view.mapToScene(view.viewport().rect().topLeft())


def _keep_place(window) -> None:
    """Remember where the sheet shown was scrolled to, its active cell and
    its workbook's zoom."""
    scene, view = window.scene, window.view
    uid = run_shown(scene)
    item = _item(window, uid)
    if item is None:
        return
    tables = view.tables
    cell = tables.active if tables.item is item else None
    corner = item.mapFromScene(_corner(view))
    scene.sheet_places[uid] = (corner, cell)
    scene.sheet_zooms[_section_key(window, uid)] = view.zoom()


# -- in and out -----------------------------------------------------------------------------------
def enter(window, uid: str, cell: Optional[tuple] = None, page: Optional[int] = None,
          keep: Optional[tuple] = None) -> bool:
    """Show sheet *uid* alone (or change to it from another sheet). *cell*:
    the cell to make active; *page*: one of its pages to show the top of;
    *keep*: (a point of the sheet, the window point to keep it under) —
    a click on its page, whose cell stays under the pointer. True when it
    is shown."""
    scene, view = window.scene, window.view
    item = _item(window, uid)
    if item is None:
        return False
    was = run_shown(scene)
    if was == uid:
        return True
    if was is None:
        # what the view was, to go back to with the ×
        scene.sheet_return = {"index": window.current_index, "zoom": view.zoom(),
                              "h": view.horizontalScrollBar().value(),
                              "v": view.verticalScrollBar().value()}
    else:
        _keep_place(window)
        old = _item(window, was)
        if old is not None and view.tables.item is old:
            view.tables.close()
    scene.sheet_view = uid
    scene.sheet_extent = (0, 0)
    view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
    item._edges = None
    item.relayout()                        # (lays the canvas out again)
    _bars(window)
    zoom = scene.sheet_zooms.get(_section_key(window, uid))
    view.set_zoom(zoom if zoom is not None else (view.zoom() if keep is not None else 1.0))
    fill(view)
    kept = scene.sheet_places.get(uid)
    if keep is not None:
        fill(view, extra=item.mapToScene(keep[0]))
        view.bring_to(item.mapToScene(keep[0]), keep[1])
    elif page is not None and page != _first_page(window, uid):
        show_page_top(window, page)
    elif kept is not None:
        view.bring_to(item.mapToScene(kept[0]), QPointF(0, 0))
    else:
        view.bring_to(item.mapToScene(item.grid_rect().topLeft()), QPointF(0, 0))
    fill(view)
    wanted = cell if cell is not None else (kept[1] if kept is not None and kept[1] else (0, 0))
    if view.tables.item is not item:
        view.tables.open(item, wanted)
    elif cell is not None:
        view.tables.select(cell)
    _chrome(window)
    return True


def leave(window, to: Optional[int] = None) -> None:
    """Back to the pages: to page *to*, or (the ×) to where the view was."""
    scene, view = window.scene, window.view
    uid = run_shown(scene)
    if uid is None:
        return
    _keep_place(window)
    item = _item(window, uid)
    if item is not None and view.tables.item is item:
        view.tables.close()
    back = scene.sheet_return or {}
    scene.sheet_view = None
    scene.sheet_extent = (0, 0)
    scene.sheet_return = None
    view.setAlignment(Qt.AlignCenter)
    if item is not None:
        item._edges = None
        item.relayout()
    else:
        scene.layout_pages()
    # the tabs and the formula bar go first: the canvas is its own height
    # again before it is put back where it was
    _bars(window)
    view.set_zoom(float(back.get("zoom", view.zoom())))
    if to is None and back:
        view.horizontalScrollBar().setValue(int(back.get("h", 0)))
        view.verticalScrollBar().setValue(int(back.get("v", 0)))
        index = int(back.get("index", window.current_index))
        index = max(0, min(index, len(window.document.pages) - 1))
        view._shown_page = index
        window.current_index = -1          # so the chrome is told, even unmoved
        window.follow_scrolled_page(index)
    _chrome(window)


def _bars(window) -> None:
    """The tabs and the formula bar as the view now is, and the window laid
    out for them at once: the canvas is its new height before it is put
    where it belongs (laid out later, it kept its middle and moved)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    tabs = getattr(window, "sheet_tabs", None)
    if tabs is not None:
        tabs.refresh()
    window.view.tables.refresh_bar()
    QApplication.sendPostedEvents(None, QEvent.LayoutRequest)


def close(window) -> None:
    """The tab strip's ×: back to the page you came from."""
    leave(window)


def sync(window) -> None:
    """After the pages changed: a sheet shown alone that has gone (deleted,
    undone) leaves the view."""
    scene = getattr(window, "scene", None)
    uid = run_shown(scene)
    from .sheetpages import run_pages
    if uid is not None and not run_pages(scene.document, uid):
        scene.sheet_view = None
        scene.sheet_extent = (0, 0)
        back = scene.sheet_return or {}
        scene.sheet_return = None
        window.view.setAlignment(Qt.AlignCenter)
        scene.layout_pages()
        if back:
            window.view.set_zoom(float(back.get("zoom", window.view.zoom())))


def _chrome(window) -> None:
    tabs = getattr(window, "sheet_tabs", None)
    if tabs is not None:
        tabs.refresh()
    headings = getattr(window.view, "sheet_headings", None)
    if headings is not None:
        headings.refresh()
    window.view.tables.refresh_bar()
    panel = getattr(window, "pages_panel", None)
    if panel is not None:
        panel.show_current(window.current_index, keep_run=True)


# -- going to a page ----------------------------------------------------------------------------------
def route(window, index: int) -> str:
    """Before going to page *index*: into the workbook view for a page of
    a sheet, out of it for any other page. Says what it did: "entered" (or
    changed sheet), "left", or ""."""
    pages = window.document.pages
    if not 0 <= index < len(pages) or window.scene is None:
        return ""
    target = pages[index].sheet
    shown = run_shown(window.scene)
    if target is not None and target != shown:
        if _item(window, target) is None:
            return ""
        enter(window, target, page=index)
        return "entered"
    if target is None and shown is not None:
        leave(window, to=index)
        return "left"
    return ""


def after_going(window, index: int, how: str) -> None:
    """After going to page *index* in the workbook view: the sheet where it
    was left (entering), or that page's first row at the top."""
    if not is_on(window):
        return
    uid = run_shown(window.scene)
    item = _item(window, uid)
    if item is None:
        return
    view = window.view
    if how == "entered":
        kept = window.scene.sheet_places.get(uid)
        if index != _first_page(window, uid):
            show_page_top(window, index)
        elif kept is not None:
            view.bring_to(item.mapToScene(kept[0]), QPointF(0, 0))
        else:
            view.bring_to(item.mapToScene(item.grid_rect().topLeft()), QPointF(0, 0))
    else:
        show_page_top(window, index)
    fill(view)
    window.current_index = index
    window.view._shown_page = index


def show_page_top(window, index: int) -> None:
    """Scroll the sheet so the first row (and column) of page *index* is at
    the top left, under the headings."""
    page = window.document.pages[index]
    item = _item(window, page.sheet)
    frame = page.frame
    if item is None or frame is None:
        return
    from ..items.table import HEADING_H, ROWNUM_W
    top_left = item.mapFromScene(frame.scenePos())
    point = QPointF(top_left.x() - ROWNUM_W if top_left.x() <= 0.5 else top_left.x(),
                    top_left.y() - HEADING_H if top_left.y() <= 0.5 else top_left.y())
    fill(window.view, extra=item.mapToScene(point))
    window.view.bring_to(item.mapToScene(point), QPointF(0, 0))


def page_key(window, step: int) -> None:
    """Ctrl+Page Down / Up: the next or previous page — in the workbook
    view, the next or previous sheet, as in Excel, and past the last or
    first sheet out to the page after or before the workbook."""
    if not is_on(window):
        window.go_to_page(window.current_index + step)
        return
    from .sheetpages import run_pages, sections
    uid = run_shown(window.scene)
    section = next((s for s in sections(window.document) if uid in s.runs), None)
    if section is None:
        window.go_to_page(window.current_index + step)
        return
    k = section.runs.index(uid) + step
    if 0 <= k < len(section.runs):
        window.go_to_page(run_pages(window.document, section.runs[k])[0])
    elif k < 0 and section.first > 0:
        window.go_to_page(section.first - 1)
    elif k >= len(section.runs) and section.last + 1 < len(window.document.pages):
        window.go_to_page(section.last + 1)


# -- the endless grid -------------------------------------------------------------------------------
#: How much more grid a scroll to the end brings, in screenfuls.
AHEAD = 1.0


def fill(view, extra: Optional[QPointF] = None) -> bool:
    """Grow the sheet shown alone so its grid fills the window (and reaches
    canvas point *extra*), and by a screenful more whenever it is scrolled
    to its end down or across: scrolled or zoomed out, there is always more
    grid. Until then the sheet is as big as its pages. True when it grew."""
    scene = view.scene()
    uid = run_shown(scene)
    if uid is None:
        return False
    from .sheetpages import run_items
    item = next((i for i in run_items(scene) if i.uid == uid and i.sheet is not None), None)
    if item is None or item.paging is None:
        return False
    seen = view.mapToScene(view.viewport().rect()).boundingRect()
    if not seen.intersects(item.mapRectToScene(item.grid_rect())):
        return False             # not showing it yet (the canvas is being laid out again)
    if extra is not None:
        seen = seen.united(seen.translated(extra - seen.topLeft()))
    local = item.mapRectFromScene(seen)

    def at_end(bar) -> bool:
        return bar.maximum() > bar.minimum() and bar.value() >= bar.maximum() - 1
    want_y = local.bottom() + (local.height() * AHEAD if at_end(view.verticalScrollBar()) else 0.0)
    want_x = local.right() + (local.width() * AHEAD if at_end(view.horizontalScrollBar()) else 0.0)
    sheet = item.sheet
    xs, ys = item.edges()
    rows, cols = len(ys) - 1, len(xs) - 1
    total_h, total_w = ys[-1], xs[-1]
    while total_h < want_y and rows < 1_048_576:          # Excel's last row
        total_h += sheet.height(rows) or sheet.default_height
        rows += 1
    while total_w < want_x and cols < 16_384:             # and its last column
        total_w += sheet.width(cols) or sheet.default_width
        cols += 1
    now = scene.sheet_extent
    if rows <= max(now[0], item.size[0]) and cols <= max(now[1], item.size[1]):
        return False
    was = item.size
    scene.sheet_extent = (max(now[0], rows), max(now[1], cols))
    item.prepareGeometryChange()
    item._edges = None
    item.update()
    scene.layout_pages()
    _keep_whole(view, item, *was)
    return True


def _keep_whole(view, item, rows: int, cols: int) -> None:
    """Whole rows or columns picked (a heading clicked) stay whole as the
    grid grows from *rows* by *cols*."""
    tables = view.tables
    if tables.item is not item:
        return
    t, l, b, r = tables.selection()
    now_rows, now_cols = item.size
    whole_rows, whole_cols = l == 0 and r == cols - 1, t == 0 and b == rows - 1
    if (whole_rows and now_cols > cols) or (whole_cols and now_rows > rows):
        tables.select((t, l), (now_rows - 1 if whole_cols else b,
                               now_cols - 1 if whole_rows else r), tables.active)


class _Watch(QObject):
    """A view's scrolling, zooming and resizing heard, to keep its sheet's
    grid filling it; and its mouse button, so a click on a sheet's cell on
    its page opens the workbook view once the button is let go (a drag to
    pick cells, or a column's edge, finishes where it began)."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self._busy = False
        self.pressed = False
        self.pending = None               # the sheet opened by the press
        for bar in (view.horizontalScrollBar(), view.verticalScrollBar()):
            bar.valueChanged.connect(self.changed)
            bar.rangeChanged.connect(self.changed)
        view.zoomChanged.connect(self.changed)
        view.viewport().installEventFilter(self)

    def changed(self, *_args) -> None:
        if self._busy or run_shown(self.view.scene()) is None:
            return
        self._busy = True
        try:
            fill(self.view)
        finally:
            self._busy = False

    def eventFilter(self, watched, event) -> bool:
        from PySide6.QtCore import QEvent
        kind = event.type()
        if kind in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            # the left button: a right-click's menu is about the page it is on
            self.pressed = event.button() == Qt.LeftButton
            self.pending = None
        elif kind == QEvent.MouseButtonRelease:
            self.pressed = False
            if self.pending is not None:
                item, self.pending = self.pending, None
                # after the view has finished with the release
                QTimer.singleShot(0, self.view, lambda: _open_alone(self.view, item))
        return False


def watch(view) -> None:
    """Keep *view*'s sheet shown alone filling it (once per view)."""
    if getattr(view, "_sheet_view_watch", None) is None:
        view._sheet_view_watch = _Watch(view)


# -- a click on a sheet's cell on its page --------------------------------------------------------
def opened(view, item) -> None:
    """A sheet opened for its cells on its pages by a click on one of them:
    the workbook view, once the button is let go. Opened any other way
    (from a menu, by a key, by the program) it stays on its pages."""
    if not getattr(item, "SHEET_RUN", False) or run_shown(view.scene()) == item.uid:
        return
    watching = getattr(view, "_sheet_view_watch", None)
    if watching is not None and watching.pressed:
        watching.pending = item


def _open_alone(view, item) -> None:
    from shiboken6 import isValid
    window = getattr(view, "window", None)
    if not isValid(view) or view.scene() is None or window is None \
            or getattr(window, "view", None) is not view:
        return
    tables = view.tables
    if tables.item is not item or run_shown(view.scene()) == item.uid:
        return
    cell = tables.active
    from .sheetpages import run_pages
    page = item.page_index_of_row(cell[0], cell[1]) if item.paging else 0
    pages = run_pages(window.document, item.uid)
    index = pages[min(page, len(pages) - 1)] if pages else window.current_index
    # the sheet stays where it is on the screen (the pages round it go), or
    # at the workbook's own zoom the cell clicked stays under the pointer
    zoom = window.scene.sheet_zooms.get(_section_key(window, item.uid))
    if zoom is None or abs(zoom - view.zoom()) < 1e-6:
        local = item.mapFromScene(_corner(view))
        where = QPointF(0, 0)
    else:
        local = item.cell_rect(cell[0], cell[1]).center()
        where = QPointF(view.mapFromScene(item.mapToScene(local)))
        if not QRectF(view.viewport().rect()).contains(where):
            where = QPointF(view.viewport().rect().center())
    rows, cols = item.size
    enter(window, item.uid, keep=(local, where))   # (the cells picked by the click stay picked)
    _reveal(view, item, cell)
    _keep_whole(view, item, rows, cols)
    window.current_index = index
    view._shown_page = index
    window.page_spin.blockSignals(True)
    window.page_spin.setValue(index + 1)
    window.page_spin.blockSignals(False)
    _chrome(window)


def _reveal(view, item, cell) -> None:
    rect = item.mapRectToScene(item.cell_rect(cell[0], cell[1]))
    fill(view, extra=rect.bottomRight())
    view.ensureVisible(rect, 40, 40)
