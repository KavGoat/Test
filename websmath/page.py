"""Page setup of a worksheet (SMath's <pageModel>): paper, margins, the
background image, and the header/footer layers drawn on every page.

SMath stores sizes in hundredths of an inch; here everything is in worksheet
pixels (96 dpi).  The header and footer layers are ordinary regions (a
picture of a company title block, text, and math regions holding *fields*
such as ``\\[TITLE]\\`` or ``\\[PAGENUM[0]]\\``) placed relative to the page's
top edge (header) or bottom margin (footer) and the left margin.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Optional

DPI = 96.0


def from_hundredths(v: float) -> float:
    return float(v) * DPI / 100.0


def to_hundredths(v: float) -> int:
    return int(round(v * 100.0 / DPI))


@dataclass
class PageSetup:
    paper_w: float = 794.0  # A4 at 96 dpi
    paper_h: float = 1123.0
    margin_l: float = 37.0
    margin_r: float = 37.0
    margin_t: float = 37.0
    margin_b: float = 37.0
    paper_id: str = "9"
    orientation: str = "Portrait"
    background: bytes = b""  # PNG/JPEG drawn on every page
    background_full_page: bool = False  # False: stretched over the printable area
    background_size: str = "stretch"
    print_grid: bool = False
    print_background: bool = True
    header: list = field(default_factory=list)  # Regions of the header layer
    footer: list = field(default_factory=list)
    # SMath's legacy header/footer strings (kept for saving)
    header_text: str = ""
    footer_text: str = ""
    header_attrs: dict = field(default_factory=dict)
    footer_attrs: dict = field(default_factory=dict)
    page_model_attrs: dict = field(default_factory=dict)

    @property
    def printable_w(self) -> float:
        return self.paper_w - self.margin_l - self.margin_r

    @property
    def printable_h(self) -> float:
        return self.paper_h - self.margin_t - self.margin_b


# -- fields: \[NAME[args]]\ --------------------------------------------------------------
FIELD_RE = re.compile(r"^\\\[(?P<name>[A-Z]+)(?:\[(?P<arg>.*)\])?\]\\$", re.S)


def is_field(text: str) -> bool:
    return bool(FIELD_RE.match(text or ""))


def _unescape(s: str) -> str:
    # SMath writes special characters in field arguments as \XXXX\ (hex)
    return re.sub(r"\\([0-9A-Fa-f]{4})\\", lambda m: chr(int(m.group(1), 16)), s)


def _date(fmt: str, now: datetime.datetime) -> str:
    fmt = _unescape(fmt) if fmt else "DD.MM.YYYY"
    out, i = [], 0
    tokens = [("YYYY", "%Y"), ("YY", "%y"), ("MMMM", "%B"), ("MMM", "%b"), ("MM", "%m"), ("DD", "%d"),
              ("HH", "%H"), ("hh", "%I"), ("mm", "%M"), ("ss", "%S"), ("tt", "%p")]
    while i < len(fmt):
        for tok, code in tokens:
            if fmt.startswith(tok, i):
                out.append(now.strftime(code))
                i += len(tok)
                break
        else:
            out.append(fmt[i])
            i += 1
    return "".join(out)


def field_text(raw: str, metadata: dict, page: int, count: int, filename: str = "",
               now: Optional[datetime.datetime] = None) -> str:
    """What a field shows on page `page` (1-based) of `count`."""
    m = FIELD_RE.match(raw or "")
    if not m:
        return raw
    name, arg = m.group("name"), m.group("arg")
    now = now or datetime.datetime.now()

    def offset():
        try:
            return int(arg) if arg else 0
        except ValueError:
            return 0

    if name == "PAGENUM":
        return str(page + offset())
    if name == "COUNT":
        return str(count + offset())
    if name == "DATE":
        return _date(arg or "", now)
    if name == "TIME":
        return _date(arg or "HH:mm", now)
    if name in ("FILENAME", "FILE"):
        return filename
    return metadata.get(name.lower(), "")
