"""How a sheet section falls onto its pages (Excel's Page Break Preview).

The user's choices (docs/SPREADSHEET_DESIGN.md): the columns that fit inside
the page's margins print, and every column after them is the scratch area,
never printed; a Print Area, or Fit to page width (which scales down), prints
more. Rows fill each page down to its bottom margin, or to a manual break;
title rows (Print Titles) repeat at the top of every page after the first.

A sheet's page options live in ``sheet.page``:

    {"fit_width": False, "fit_tall": 0, "scale": 100, "print_area": None or [t, l, b, r],
     "titles": None or [first_row, last_row], "title_cols": None or [first, last],
     "breaks": [row, ...], "col_breaks": [col, ...],
     "center_h": False, "center_v": False,
     "print_gridlines": False, "print_headings": False}
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULTS = {"fit_width": False, "fit_tall": 0, "scale": 100, "print_area": None, "titles": None,
            "title_cols": None, "breaks": [], "col_breaks": [],
            "center_h": False, "center_v": False, "print_gridlines": False,
            "print_headings": False}

HEADING_W = 22.0      # printed row numbers' strip, when headings are printed
HEADING_H = 12.0


def options(sheet) -> dict:
    page = getattr(sheet, "page", None) or {}
    out = dict(DEFAULTS)
    out.update(page)
    return out


@dataclass
class Paging:
    printable: tuple            # (left, top, width, height) of the paper's printable area, pt
    paper: tuple                # (width, height), pt
    scale: float                # printed size / on-screen size (Adjust to %, or Fit to)
    first_col: int
    last_col: int               # the last column printed
    slices: list = field(default_factory=list)   # (first row, last row) of each page
    manual: set = field(default_factory=set)     # rows where a manual break starts a page
    titles: tuple = None
    shown_cols: int = 0          # columns shown on screen (printed + scratch)
    print_rows: tuple = None     # (first, last) rows printed, from a print area
    title_cols: tuple = None     # columns printed at the left of every page (Print Titles)
    groups: list = field(default_factory=list)   # (first col, last col) of each page across
    col_manual: set = field(default_factory=set)  # columns where a manual break starts a page

    def __post_init__(self):
        if not self.groups:
            self.groups = [(self.first_col, self.last_col)]

    @property
    def pages(self) -> int:
        return len(self.slices) * len(self.groups)

    def page_of(self, k: int) -> tuple:
        """(row slice, column group) of the run's k-th page: down, then over (Excel's order)."""
        down = max(1, len(self.slices))
        return k % down, k // down

    def index_of(self, slice_index: int, group: int) -> int:
        return group * max(1, len(self.slices)) + slice_index


def paginate(sheet, setup, pages_wanted: int = 1) -> Paging:
    """The run's pages: at least pages_wanted, and as many as its content needs."""
    opts = options(sheet)
    left, top, width, height = setup.content_rect_pt
    headings = opts["print_headings"]
    if headings:
        width -= HEADING_W
        height -= HEADING_H
    data = sheet.data_area()
    area = opts["print_area"]
    # Fit to N pages wide (True is 1) by M tall (0: as many as it takes)
    fit_wide = int(opts["fit_width"] or 0)
    fit_tall = max(0, int(opts.get("fit_tall") or 0))
    fitting = bool(fit_wide or fit_tall)
    # Excel's Adjust to % (ignored when fitting to pages, as in Excel)
    adjust = 1.0 if fitting else max(10, min(400, int(opts.get("scale") or 100))) / 100.0
    col_breaks = set(int(c) for c in opts.get("col_breaks") or [])
    first_col = area[1] if area else 0
    # where the printed columns end: the print area's edge; or, fitting, the
    # data's; or else the page that fits, and one more for each break after it
    end_col = area[3] if area else (max(data[3], 0) if fitting and data is not None else None)
    titles_cols = tuple(opts["title_cols"]) if opts.get("title_cols") else None
    title_w = sum(sheet.width(c) for c in range(titles_cols[0], titles_cols[1] + 1)) \
        if titles_cols else 0.0

    def col_groups(scale: float) -> list:
        """The pages across (Excel's vertical page breaks, automatic and
        manual), each room left for the columns repeated at the left."""
        room = width / scale
        groups = []
        c = first_col
        while True:
            start = c
            reserve = title_w if titles_cols and start > titles_cols[1] else 0.0
            used = 0.0
            while True:
                if end_col is not None and c > end_col:
                    break
                w = sheet.width(c)
                if c > start and (used + w > room - reserve + 0.01 or c in col_breaks):
                    break
                used += w
                c += 1
                if c - start > 2000:
                    break
            groups.append((start, max(start, c - 1)))
            if end_col is not None:
                if c > end_col:
                    break
            elif not any(b >= c for b in col_breaks):
                break
            if len(groups) > 200:
                break
        return groups

    # and rows to repeat at the top: on every page whose own rows start below them
    titles = tuple(opts["titles"]) if opts["titles"] else None
    titles_h = sum(sheet.height(r) for r in range(titles[0], titles[1] + 1)) if titles else 0.0
    breaks = set(int(b) for b in opts["breaks"])
    last_needed = data[2] if data is not None else 0
    if area:
        last_needed = max(last_needed, area[2])
    elif breaks:
        # the page a manual break starts is there even with nothing on it
        # yet, as in Excel's Page Layout view: the rows after the break are
        # somewhere to type, not cut off (the user, 2026-10-15)
        last_needed = max(last_needed, max(breaks))
    first_row = area[0] if area else 0

    def slice_rows(scale: float, wanted: int) -> list:
        room = height / scale
        slices = []
        row = 0
        while True:
            start = row
            shown_from = max(start, first_row)
            avail = room - (titles_h if titles and shown_from > titles[1] else 0.0)
            used = 0.0
            while True:
                h = sheet.height(row)
                if row > start and (used + h > avail + 0.01 or row in breaks):
                    break
                used += h
                row += 1
                if row - start > 5000:
                    break
            slices.append((start, row - 1))
            if len(slices) >= wanted and row > last_needed:
                break
            if len(slices) > 2000:
                break
        return slices

    def counted(slices) -> int:
        return len([s for s in slices if s[0] <= last_needed and s[1] >= first_row])

    scale = adjust
    if fitting:
        # Excel's Fit to: a whole percentage, never above 100% nor under 10%
        best = 1.0
        if fit_wide and end_col is not None:
            wide = sum(sheet.width(c) for c in range(first_col, end_col + 1)) + \
                (title_w if titles_cols and first_col > titles_cols[1] else 0.0)
            if wide > fit_wide * width:
                best = min(best, fit_wide * width / wide)
        if fit_tall:
            tall = sum(sheet.height(r) for r in range(first_row, last_needed + 1))
            if tall > fit_tall * height:
                best = min(best, fit_tall * height / tall)
        scale = max(10, min(100, int(best * 100 + 1e-9))) / 100.0
    while True:
        groups = col_groups(scale)
        wanted = -(-max(1, pages_wanted) // len(groups))
        slices = slice_rows(scale, wanted)
        too_wide = fit_wide and len(groups) > fit_wide
        too_tall = fit_tall and counted(slices) > fit_tall
        if not (too_wide or too_tall) or scale <= 0.1:
            break
        scale = round(scale - 0.01, 2)           # rows and columns don't split: a step smaller
    first_col, last_col = groups[0][0], groups[-1][1]
    paper = (setup.width_pt, setup.height_pt)
    # on screen: the printed columns, then scratch at least a page wide
    scratch, c = 0.0, last_col + 1
    while scratch < paper[0]:
        scratch += max(sheet.width(c), 1.0)
        c += 1
    shown = max(c, (data[3] + 2) if data is not None else 0)
    print_rows = (area[0], area[2]) if area else None
    title_cols = titles_cols if titles_cols and any(g[0] > titles_cols[1] for g in groups) else None
    return Paging((left, top, width, height), paper, scale, first_col, last_col, slices,
                  breaks, titles, shown, print_rows, title_cols, groups, col_breaks)


def pages_needed(sheet, setup) -> int:
    return paginate(sheet, setup, 1).pages


def page_of_row(paging: Paging, row: int) -> int:
    for k, (a, b) in enumerate(paging.slices):
        if a <= row <= b:
            return k
    return len(paging.slices) - 1
