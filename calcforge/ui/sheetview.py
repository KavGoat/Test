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


#: Excel's 100 %: its cells drawn at 96 pixels an inch, where the canvas
#: draws a point a pixel (72 an inch). In the workbook view the zoom box's
#: 100 % is Excel's — a default column 64 px wide, a row 20 px — and the
#: pages and printing stay as they are (the user's answer, H1).
EXCEL_SCALE = 96.0 / 72.0

#: Excel's Ctrl+wheel zoom: steps of 15 %, 10 % to 400 % (K1)
WHEEL_STEP, ZOOM_MIN, ZOOM_MAX = 15, 10, 400

#: Rows a notch of the wheel scrolls (Windows' "3 lines", Excel's rows: F6)
WHEEL_ROWS = 3


def run_shown(scene) -> Optional[str]:
    """The sheet (run id) shown alone on *scene*, or None for the pages."""
    return getattr(scene, "sheet_view", None) if scene is not None else None


def is_on(window) -> bool:
    return run_shown(getattr(window, "scene", None)) is not None


def shown_zoom(view, zoom: Optional[float] = None) -> float:
    """The zoom as the zoom box says it: Excel's in the workbook view."""
    zoom = view.zoom() if zoom is None else zoom
    return zoom / EXCEL_SCALE if run_shown(view.scene()) is not None else zoom


def view_zoom(view, shown: float) -> float:
    """The canvas zoom for the zoom box's *shown* (Excel's in the workbook view)."""
    return shown * EXCEL_SCALE if run_shown(view.scene()) is not None else shown


def wheel_zoom_factor(view, delta: int) -> Optional[float]:
    """Ctrl+wheel in the workbook view: Excel's 15 % steps (10 %, 25 %, 40 %
    … 100 %, 115 % …), as a factor of the zoom now; None elsewhere."""
    if run_shown(view.scene()) is None or not delta:
        return None
    import math
    now = shown_zoom(view) * 100.0
    k = (now - ZOOM_MIN) / WHEEL_STEP
    notches = max(1, int(round(abs(delta) / 120.0)))
    k = (math.floor(k + 1e-6) + notches) if delta > 0 else (math.ceil(k - 1e-6) - notches)
    wanted = max(ZOOM_MIN, min(ZOOM_MAX, ZOOM_MIN + WHEEL_STEP * k))
    return wanted / now if now > 0 else None


def wheel_pixels(view) -> Optional[float]:
    """How far a notch of the wheel scrolls in the workbook view: three of
    its rows (Excel's), in pixels at the zoom; None elsewhere."""
    scene = view.scene()
    uid = run_shown(scene)
    if uid is None:
        return None
    from .sheetpages import run_items
    item = next((i for i in run_items(scene) if i.uid == uid and i.sheet is not None), None)
    height = item.sheet.default_height if item is not None else 15.0
    return WHEEL_ROWS * height * view.zoom()


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
    view.set_zoom(zoom if zoom is not None else EXCEL_SCALE)      # Excel's 100 %
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
    shows = getattr(window, "_show_zoom", None)
    if shows is not None:
        shows(window.view.zoom())               # Excel's % in the workbook view
    from . import sheetfreeze, sheetstatus
    sheetstatus.refresh(window)
    sheetfreeze.refresh(window.view)


# -- Normal view and Page Break Preview (I1, D2) -----------------------------------------------------
NORMAL, PAGE_LAYOUT, BREAK_PREVIEW = "normal", "page_layout", "break_preview"


def sheet_mode(item) -> str:
    """How a sheet shown alone is viewed: Excel's Normal view, or Page
    Break Preview (kept with the sheet, as Excel keeps it)."""
    sheet = getattr(item, "sheet", None)
    page = getattr(sheet, "page", None) or {}
    return BREAK_PREVIEW if page.get("view") == BREAK_PREVIEW else NORMAL


def breaks_editable(item) -> bool:
    """Whether a sheet's page breaks and print area's edges can be dragged:
    on its pages, and in Page Break Preview — never in Normal view, where
    Excel's page lines are only lines (B1)."""
    return not getattr(item, "alone", False) or sheet_mode(item) == BREAK_PREVIEW


def current_view(window) -> str:
    """Normal, Page Layout (the pages) or Page Break Preview: the status
    bar's view buttons."""
    item = _item(window, run_shown(getattr(window, "scene", None)))
    if item is None:
        return PAGE_LAYOUT
    return sheet_mode(item)


def set_view(window, which: str) -> None:
    """Excel's view buttons: Normal (the workbook view), Page Layout (the
    sheet's pages) and Page Break Preview (the workbook view with the print
    area white, the rest grey, the breaks blue and dragged)."""
    scene = getattr(window, "scene", None)
    if scene is None:
        return
    index = window.current_index
    pages = window.document.pages
    if which == PAGE_LAYOUT:
        if is_on(window):
            leave(window, to=index)
            window.go_to_page(index)
        return
    uid = run_shown(scene)
    if uid is None:
        if not (0 <= index < len(pages)) or pages[index].sheet is None:
            window.status_hint.setText("Normal and Page Break Preview are for a spreadsheet page")
            return
        window.go_to_page(index)
        uid = run_shown(scene)
    item = _item(window, uid)
    if item is None:
        return
    if sheet_mode(item) != which:
        if item.sheet.page is None:
            item.sheet.page = {}
        if which == BREAK_PREVIEW:
            item.sheet.page["view"] = BREAK_PREVIEW
        else:
            item.sheet.page.pop("view", None)
        window.mark_modified()
        item._edges = None
        item.prepareGeometryChange()
        item.update()
    _chrome(window)


def page_rows(view, item) -> int:
    """Rows a screenful holds in the workbook view (Page Down's step), or 0."""
    if not getattr(item, "alone", False):
        return 0
    seen = item.mapRectFromScene(view.mapToScene(view.viewport().rect()).boundingRect())
    import bisect
    xs, ys = item.edges()
    top = max(0, bisect.bisect_left(ys, seen.top() + HEADING_PAD))
    bottom = max(top, bisect.bisect_right(ys, seen.bottom()) - 1)
    return max(1, bottom - top)


def current_region(sheet, cell: tuple) -> Optional[tuple]:
    """Excel's current region round *cell*: the block bounded by empty
    rows and columns (top, left, bottom, right), or None when *cell* and
    every cell touching it are empty."""
    filled = {pos for pos, c in sheet.cells.items()
              if c.input not in (None, "") or c.value not in (None, "")}
    t = b = cell[0]
    l = r = cell[1]
    grew = True
    while grew:
        grew = False
        if t > 0 and any((t - 1, c) in filled for c in range(max(0, l - 1), r + 2)):
            t -= 1
            grew = True
        if any((b + 1, c) in filled for c in range(max(0, l - 1), r + 2)):
            b += 1
            grew = True
        if l > 0 and any((rr, l - 1) in filled for rr in range(max(0, t - 1), b + 2)):
            l -= 1
            grew = True
        if any((rr, r + 1) in filled for rr in range(max(0, t - 1), b + 2)):
            r += 1
            grew = True
    if (t, l, b, r) == (cell[0], cell[1], cell[0], cell[1]) and cell not in filled:
        return None
    return (t, l, b, r)


#: (the headings at the top of the window cover a row's worth)
HEADING_PAD = 12.0


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
#: How much grid there is past what is seen, in screenfuls.
AHEAD = 1.0

#: The grid grows and shrinks by whole blocks of rows and columns, so the
#: canvas is laid out again now and then, not at every notch of the wheel.
ROW_BLOCK, COL_BLOCK = 50, 10


def fill(view, extra: Optional[QPointF] = None) -> bool:
    """The sheet shown alone's grid: as far as the window sees (and canvas
    point *extra*) and a screenful more, never less than its pages and
    its cells picked. Scrolled or zoomed out, there is always more grid;
    scrolled back, it shrinks again, so the scroll bar's thumb is as big
    as the sheet in use allows (Excel's: A3) — not while the thumb is held.
    True when it changed."""
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

    want_y = local.bottom() + local.height() * AHEAD
    want_x = local.right() + local.width() * AHEAD
    sheet = item.sheet
    xs, ys = item.edges()
    rows = _reach(ys, want_y, lambda r: sheet.height(r) or sheet.default_height, 1_048_576)
    cols = _reach(xs, want_x, lambda c: sheet.width(c) or sheet.default_width, 16_384)
    rows = min(1_048_576, -(-rows // ROW_BLOCK) * ROW_BLOCK)
    cols = min(16_384, -(-cols // COL_BLOCK) * COL_BLOCK)
    # never less than the cells picked and the active cell
    tables = view.tables
    if tables.item is item:
        t, l, b, r = tables.selection()
        rows, cols = max(rows, b + 1, tables.active[0] + 1), max(cols, r + 1, tables.active[1] + 1)
    now = scene.sheet_extent
    held = view.verticalScrollBar().isSliderDown() or view.horizontalScrollBar().isSliderDown()
    if held:
        rows, cols = max(rows, now[0]), max(cols, now[1])
    if (rows, cols) == tuple(now):
        return False
    was = item.size
    scene.sheet_extent = (rows, cols)
    if item.size == was:
        return False
    item.prepareGeometryChange()
    item._edges = None
    item.update()
    scene.layout_pages()
    _keep_whole(view, item, *was)
    return True


def reach(view, item, cell: tuple) -> bool:
    """The grid of the sheet shown alone grown to hold *cell* (Ctrl+↓ to
    Excel's last row). True when it does."""
    scene = view.scene()
    if run_shown(scene) != getattr(item, "uid", None):
        return False
    rows, cols = scene.sheet_extent
    want = (max(rows, cell[0] + 1), max(cols, cell[1] + 1))
    if want != tuple(scene.sheet_extent):
        was = item.size
        scene.sheet_extent = want
        item.prepareGeometryChange()
        item._edges = None
        item.update()
        scene.layout_pages()
        _keep_whole(view, item, *was)
    return item.size[0] > cell[0] and item.size[1] > cell[1]


def _reach(edges: list, want: float, size, limit: int) -> int:
    """How many rows (or columns) reach *want*: those of *edges*, and as
    many more of *size* as it takes, up to *limit*."""
    import bisect
    if want <= edges[-1]:
        return max(1, bisect.bisect_left(edges, want))
    count, total = len(edges) - 1, edges[-1]
    while total < want and count < limit:
        total += size(count)
        count += 1
    return count


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
        # (once the view has scrolled to where the thumb was dragged)
        view.verticalScrollBar().sliderMoved.connect(
            lambda _v: QTimer.singleShot(0, self, lambda: self.tip(True)))
        view.horizontalScrollBar().sliderMoved.connect(
            lambda _v: QTimer.singleShot(0, self, lambda: self.tip(False)))
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

    def tip(self, down: bool) -> None:
        """Excel's tip as the thumb is dragged: the row (or column) at the
        top (left) of the window (A5)."""
        view = self.view
        scene = view.scene()
        uid = run_shown(scene)
        if uid is None:
            return
        from .sheetpages import run_items
        item = next((i for i in run_items(scene) if i.uid == uid and i.sheet is not None), None)
        if item is None:
            return
        import bisect

        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QToolTip

        from ..items.table import HEADING_H, ROWNUM_W
        from ..sheet.refs import col_letters
        corner = item.mapFromScene(_corner(view))
        xs, ys = item.edges()
        if down:
            row = max(0, bisect.bisect_right(ys, corner.y() + HEADING_H) - 1)
            text = f"Row: {row + 1}"
        else:
            col = max(0, bisect.bisect_right(xs, corner.x() + ROWNUM_W) - 1)
            text = f"Column: {col_letters(col)}"
        self.last_tip = text
        QToolTip.showText(QCursor.pos(), text, view)

    last_tip = ""

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
