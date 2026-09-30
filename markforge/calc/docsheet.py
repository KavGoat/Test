"""One worksheet for the whole document (decision 9).

Every equation in the document is a region of one WebSMath ``Worksheet``, so
a variable defined on page 1 is known on page 5, and evaluation runs as SMath
runs it: page 1 top-left to bottom-right, then page 2, and so on.

The worksheet orders regions by ``(y, x, id)``. It is kept exactly as WebSMath
has it; the page is folded into ``y`` instead. A region's worksheet position is

    x = its x on the page, in SMath pixels
    y = (the page's place in the document) · STRIDE + its y on the page

where the page coordinates are the page's own, unrotated ones — so turning a
page never changes a result, and moving a page changes the order exactly as
moving its equations would. STRIDE is far taller than any sheet.

The equations themselves are page items (``items/calc.py``); this only keeps
their regions in step with where they are, and says which of them need
redrawing after a calculation.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Optional

from .worksheet import Region, Worksheet

# One SMath pixel is 1/96 inch; a page point is 1/72 inch.
PT_PER_PX = 0.75
PX_PER_PT = 1.0 / PT_PER_PX
STRIDE = 1_000_000.0


class DocumentSheet:
    """The document's worksheet and the page each region is on."""

    def __init__(self, document):
        self.document = document
        self.worksheet = Worksheet()
        self._page_of: dict[int, str] = {}          # region id -> page uid
        self._local: dict[int, tuple] = {}          # region id -> (x_px, y_px) on its page
        self._order_seen: tuple = ()
        self._batch = 0
        self._dirty = False
        # Told which regions' shown results changed, so their items redraw.
        self.on_changed: Optional[Callable[[set], None]] = None

    # -- where things are ----------------------------------------------------
    def _page_orders(self) -> dict[str, int]:
        return {page.uid: index for index, page in enumerate(self.document.pages)}

    def _place(self, region: Region, orders: dict) -> None:
        x, y = self._local[region.id]
        order = orders.get(self._page_of[region.id], len(orders))
        region.x = x
        region.y = order * STRIDE + y

    def page_uid(self, region: Region) -> Optional[str]:
        return self._page_of.get(region.id)

    def local_position(self, region: Region) -> Optional[tuple]:
        return self._local.get(region.id)

    # -- regions coming and going ----------------------------------------------
    def add(self, data: dict, page_uid: str, x_px: float, y_px: float) -> Region:
        from .record import add_region_from_data

        region = add_region_from_data(self.worksheet, x_px, y_px, data)
        self._page_of[region.id] = page_uid
        self._local[region.id] = (float(x_px), float(y_px))
        self._place(region, self._page_orders())
        self.worksheet.invalidate_order()
        self._settle_region(region)
        return region

    def remove(self, region: Region) -> None:
        if region not in self.worksheet.regions:
            return
        self.worksheet.remove_region(region)
        self._page_of.pop(region.id, None)
        self._local.pop(region.id, None)
        if self._batch:
            self._dirty = True
            return
        if self.worksheet.auto_calculation:
            self.worksheet.region_removed(region)
        self._report()

    def move(self, region: Region, page_uid: str, x_px: float, y_px: float) -> None:
        """A region was put somewhere else (dragged, nudged, or its page moved)."""
        if (self._page_of.get(region.id), self._local.get(region.id)) == \
                (page_uid, (float(x_px), float(y_px))):
            return
        self._page_of[region.id] = page_uid
        self._local[region.id] = (float(x_px), float(y_px))
        self._place(region, self._page_orders())
        self._settle_region(region)

    def edited(self, region: Region) -> None:
        """A region was left after editing: bring what depends on it up to date."""
        self._settle_region(region)

    # -- calculating -------------------------------------------------------------
    def _settle_region(self, region: Region) -> None:
        if self._batch:
            self._dirty = True
            return
        if self._pages_moved():
            return
        if self.worksheet.auto_calculation:
            # a changed key is a moved region; the worksheet then recalculates
            # everything, as the reading order may have changed
            self.worksheet.update_after_edit(region)
        self._report()

    def _pages_moved(self) -> bool:
        """Pages reordered, inserted or deleted since the last look: re-key all."""
        now = tuple(page.uid for page in self.document.pages)
        if now == self._order_seen:
            return False
        self._order_seen = now
        orders = self._page_orders()
        for region in self.worksheet.regions:
            if region.id in self._local:
                self._place(region, orders)
        self.worksheet.invalidate_order()
        self.recalculate()
        return True

    def pages_changed(self) -> None:
        if self._batch:
            self._dirty = True
            return
        self._pages_moved()

    def recalculate(self, force: bool = False) -> None:
        """Everything, in reading order (F9, loading, pages moved)."""
        self._order_seen = tuple(page.uid for page in self.document.pages)
        if self.worksheet.auto_calculation or force:
            self.worksheet.calculate()
        self._report()

    def _report(self) -> None:
        changed = self.worksheet.take_changed()
        if self.on_changed is not None:
            self.on_changed(changed)

    @contextmanager
    def batch(self):
        """Many regions arriving at once (a page restored by undo, a document
        opening): one calculation at the end instead of one per region."""
        self._batch += 1
        try:
            yield
        finally:
            self._batch -= 1
            if not self._batch and self._dirty:
                self._dirty = False
                self.recalculate()

    # -- asking ------------------------------------------------------------------------
    def region_by_id(self, region_id: int) -> Optional[Region]:
        for region in self.worksheet.regions:
            if region.id == region_id:
                return region
        return None


def sheet_for(document) -> DocumentSheet:
    """The document's sheet, made the first time it is asked for."""
    sheet = getattr(document, "_calc_sheet", None)
    if sheet is None:
        sheet = DocumentSheet(document)
        document._calc_sheet = sheet
    return sheet
