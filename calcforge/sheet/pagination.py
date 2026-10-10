"""How a sheet section falls onto its pages (Excel's Page Break Preview).

The user's choices (docs/SPREADSHEET_DESIGN.md): the columns that fit inside
the page's margins print, and every column after them is the scratch area,
never printed; a Print Area, or Fit to page width (which scales down), prints
more. Rows fill each page down to its bottom margin, or to a manual break;
title rows (Print Titles) repeat at the top of every page after the first.

A sheet's page options live in ``sheet.page``:

    {"fit_width": False, "fit_tall": 0, "scale": 100, "print_area": None or [t, l, b, r],
     "titles": None or [first_row, last_row], "breaks": [row, ...],
     "center_h": False, "center_v": False,
     "print_gridlines": False, "print_headings": False}
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULTS = {"fit_width": False, "fit_tall": 0, "scale": 100, "print_area": None, "titles": None, "breaks": [],
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

    @property
    def pages(self) -> int:
        return len(self.slices)


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
    fit_wide, fit_tall = bool(opts["fit_width"]), max(0, int(opts.get("fit_tall") or 0))
    fitting = fit_wide or fit_tall
    # Excel's Adjust to % (ignored when fitting to pages, as in Excel)
    adjust = 1.0 if fitting else max(10, min(400, int(opts.get("scale") or 100))) / 100.0
    # the columns printed
    if area:
        first_col, last_col = area[1], area[3]
    else:
        first_col = 0
        if fitting and data is not None:
            last_col = max(data[3], 0)
        else:
            x, c = 0.0, 0
            while True:
                w = sheet.width(c)
                if (x + w) * adjust > width + 0.01 and c > 0:
                    break
                x += w
                c += 1
                if c > 2000:
                    break
            last_col = max(c - 1, 0)
    printed_w = sum(sheet.width(c) for c in range(first_col, last_col + 1))
    # title rows
    titles = tuple(opts["titles"]) if opts["titles"] else None
    titles_h = sum(sheet.height(r) for r in range(titles[0], titles[1] + 1)) if titles else 0.0
    breaks = set(int(b) for b in opts["breaks"])
    last_needed = data[2] if data is not None else 0
    if area:
        last_needed = max(last_needed, area[2])
    first_row = area[0] if area else 0

    def slice_rows(scale: float) -> list:
        room = height / scale
        slices = []
        row = 0
        while True:
            start = row
            avail = room - (titles_h if titles and slices and start > titles[1] else 0.0)
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
            if len(slices) >= pages_wanted and row > last_needed:
                break
            if len(slices) > 2000:
                break
        return slices

    scale = adjust
    if fitting:
        # Excel's Fit to: a whole percentage, never above 100% nor under 10%
        best = 1.0
        if fit_wide and printed_w > width:
            best = min(best, width / printed_w)
        if fit_tall:
            tall = sum(sheet.height(r) for r in range(first_row, last_needed + 1))
            if tall > fit_tall * height:
                best = min(best, fit_tall * height / tall)
        scale = max(10, min(100, int(best * 100 + 1e-9))) / 100.0
    slices = slice_rows(scale)
    while fit_tall and scale > 0.1 and \
            len([s for s in slices if s[0] <= last_needed and s[1] >= first_row]) > fit_tall:
        scale = round(scale - 0.01, 2)           # rows don't split: a step smaller, as Excel
        slices = slice_rows(scale)
    paper = (setup.width_pt, setup.height_pt)
    # on screen: the printed columns, then scratch at least a page wide
    scratch, c = 0.0, last_col + 1
    while scratch < paper[0]:
        scratch += max(sheet.width(c), 1.0)
        c += 1
    shown = max(c, (data[3] + 2) if data is not None else 0)
    print_rows = (area[0], area[2]) if area else None
    return Paging((left, top, width, height), paper, scale, first_col, last_col, slices,
                  breaks, titles, shown, print_rows)


def pages_needed(sheet, setup) -> int:
    return paginate(sheet, setup, 1).pages


def page_of_row(paging: Paging, row: int) -> int:
    for k, (a, b) in enumerate(paging.slices):
        if a <= row <= b:
            return k
    return len(paging.slices) - 1
