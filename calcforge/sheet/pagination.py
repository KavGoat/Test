"""How a sheet section falls onto its pages (Excel's Page Break Preview).

The user's choices (docs/SPREADSHEET_DESIGN.md): the columns that fit inside
the page's margins print, and every column after them is the scratch area,
never printed; a Print Area, or Fit to page width (which scales down), prints
more. Rows fill each page down to its bottom margin, or to a manual break;
title rows (Print Titles) repeat at the top of every page after the first.

A sheet's page options live in ``sheet.page``:

    {"fit_width": False, "print_area": None or [t, l, b, r],
     "titles": None or [first_row, last_row], "breaks": [row, ...],
     "center_h": False, "center_v": False,
     "print_gridlines": False, "print_headings": False}
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULTS = {"fit_width": False, "print_area": None, "titles": None, "breaks": [],
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
    scale: float                # printed size / on-screen size (Fit to page width)
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
    # the columns printed
    if area:
        first_col, last_col = area[1], area[3]
    else:
        first_col = 0
        if opts["fit_width"] and data is not None:
            last_col = max(data[3], 0)
        else:
            x, c = 0.0, 0
            while True:
                w = sheet.width(c)
                if x + w > width + 0.01 and c > 0:
                    break
                x += w
                c += 1
                if c > 2000:
                    break
            last_col = max(c - 1, 0)
    printed_w = sum(sheet.width(c) for c in range(first_col, last_col + 1))
    scale = 1.0
    if (opts["fit_width"] or area) and printed_w > width:
        scale = width / printed_w if opts["fit_width"] else 1.0
    # title rows
    titles = tuple(opts["titles"]) if opts["titles"] else None
    titles_h = sum(sheet.height(r) for r in range(titles[0], titles[1] + 1)) if titles else 0.0
    breaks = set(int(b) for b in opts["breaks"])
    room = height / scale
    slices = []
    row = 0
    last_needed = data[2] if data is not None else 0
    if area:
        last_needed = max(last_needed, area[2])
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
