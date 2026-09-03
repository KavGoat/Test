"""Document, page and scale model."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any, Optional

from .engine import Workspace
from .units import Q_, format_quantity, parse_unit

MM_TO_PT = 72.0 / 25.4
PT_TO_MM = 25.4 / 72.0
IN_TO_PT = 72.0

# Width x height in millimetres, portrait.
PAGE_SIZES: dict[str, tuple[float, float]] = {
    "A0": (841.0, 1189.0),
    "A1": (594.0, 841.0),
    "A2": (420.0, 594.0),
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
    "Tabloid": (279.4, 431.8),
    "ANSI A": (215.9, 279.4),
    "ANSI B": (279.4, 431.8),
    "ANSI C": (431.8, 558.8),
    "ANSI D": (558.8, 863.6),
    "ANSI E": (863.6, 1117.6),
    "ARCH D": (609.6, 914.4),
    "ARCH E": (914.4, 1219.2),
}

PORTRAIT = "portrait"
LANDSCAPE = "landscape"


@dataclass
class PageSetup:
    """Physical page geometry.  Defaults to A4 portrait."""

    size_name: str = "A4"
    width_mm: float = 210.0
    height_mm: float = 297.0
    orientation: str = PORTRAIT
    # Even margins, so the printable area sits in the middle of the sheet.
    # Ten millimetres is the narrowest most printers will hold, and a
    # calculation sheet wants the paper it is paying for: wider than this and
    # the page reads as a frame with a little writing in it.
    margin_left: float = 10.0
    margin_top: float = 10.0
    margin_right: float = 10.0
    margin_bottom: float = 10.0

    @classmethod
    def from_name(cls, name: str, orientation: str = PORTRAIT) -> "PageSetup":
        width, height = PAGE_SIZES.get(name, PAGE_SIZES["A4"])
        setup = cls(size_name=name, width_mm=width, height_mm=height, orientation=orientation)
        return setup

    def apply_size(self, name: str) -> None:
        if name in PAGE_SIZES:
            self.size_name = name
            self.width_mm, self.height_mm = PAGE_SIZES[name]

    @property
    def width_pt(self) -> float:
        mm = self.height_mm if self.orientation == LANDSCAPE else self.width_mm
        return mm * MM_TO_PT

    @property
    def height_pt(self) -> float:
        mm = self.width_mm if self.orientation == LANDSCAPE else self.height_mm
        return mm * MM_TO_PT

    @property
    def content_rect_pt(self) -> tuple[float, float, float, float]:
        """x, y, width, height of the printable area in points."""
        left = self.margin_left * MM_TO_PT
        top = self.margin_top * MM_TO_PT
        width = self.width_pt - (self.margin_left + self.margin_right) * MM_TO_PT
        height = self.height_pt - (self.margin_top + self.margin_bottom) * MM_TO_PT
        return left, top, max(width, 1.0), max(height, 1.0)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PageSetup":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


@dataclass
class PageScale:
    """Drawing scale used by the measurement tools.

    ``length_per_pt`` is the real-world length represented by one point on the
    page, stored as a pint quantity so measurements come out unit-aware.
    """

    label: str = "1:1"
    length_per_pt: Any = None          # Quantity, e.g. 1 pt -> 35.28 mm at 1:100
    precision: int = 2
    display_unit: str = "m"
    area_unit: str = "m^2"

    def __post_init__(self):
        if self.length_per_pt is None:
            self.length_per_pt = Q_(1.0 / MM_TO_PT, "mm")

    @classmethod
    def from_ratio(cls, ratio: float, display_unit: str = "m") -> "PageScale":
        """``ratio`` of 100 means 1:100 — one page mm is 100 real mm."""
        scale = cls(label=f"1:{ratio:g}", display_unit=display_unit)
        scale.length_per_pt = Q_(ratio * PT_TO_MM, "mm")
        return scale

    @classmethod
    def from_calibration(cls, page_distance_pt: float, real_length_text: str,
                         display_unit: str = "m") -> "PageScale":
        """Build a scale from a drawn distance and the length it represents."""
        real = parse_unit(real_length_text)
        if real is None or page_distance_pt <= 0:
            return cls()
        per_pt = real / page_distance_pt
        scale = cls(label=f"{format_quantity(real, 4)} = {page_distance_pt:.1f} pt",
                    display_unit=display_unit)
        scale.length_per_pt = per_pt
        return scale

    def length(self, points: float):
        return self.length_per_pt * points

    def area(self, square_points: float):
        return (self.length_per_pt ** 2) * square_points

    def is_calibrated(self) -> bool:
        return self.label != "1:1"

    def to_dict(self) -> dict:
        quantity = self.length_per_pt
        return {
            "label": self.label,
            "magnitude": float(quantity.magnitude),
            "units": str(quantity.units),
            "precision": self.precision,
            "display_unit": self.display_unit,
            "area_unit": self.area_unit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PageScale":
        scale = cls(label=data.get("label", "1:1"),
                    precision=int(data.get("precision", 2)),
                    display_unit=data.get("display_unit", "m"),
                    area_unit=data.get("area_unit", "m^2"))
        try:
            scale.length_per_pt = Q_(float(data["magnitude"]), data["units"])
        except Exception:
            pass
        return scale


@dataclass
class Layer:
    name: str
    visible: bool = True
    locked: bool = False
    printable: bool = True
    color: str = "#8899aa"


@dataclass
class Bookmark:
    """A named place in the document.

    Kept against the page's own id rather than its number, so reordering or
    inserting pages does not send every bookmark to the wrong sheet. *y* is
    how far down that page it points, in points.
    """

    title: str
    page_uid: str
    y: float = 0.0
    level: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Bookmark":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


class Page:
    """One sheet of the document."""

    def __init__(self, setup: Optional[PageSetup] = None, label: str = ""):
        self.uid = uuid.uuid4().hex
        self.setup = setup or PageSetup.from_name("A4")
        self.scale = PageScale()
        self.label = label
        self.background_key: Optional[str] = None   # asset name of an imported PDF page
        self.background_opacity: float = 1.0
        self.source_note: str = ""                  # e.g. "drawing.pdf page 3"
        # Whether this page carries a grid. A page written on wants one; a
        # drawing that came in on a PDF has its own lines and a grid over the
        # top only gets in the way, so an inserted page comes in without one.
        # None means "whatever the document says", which is what a page saved
        # before pages had their own grid comes back as.
        self.grid: Optional[bool] = None
        # The same for the running header and footer: a page can be left out
        # of them — a drawing sheet with its own title block does not want a
        # second one written over it. None means "as the document says".
        self.header: Optional[bool] = None
        self.footer: Optional[bool] = None
        self.frame = None                           # set by the UI layer
        self._pending_items: list[dict] = []

    # -- geometry ----------------------------------------------------------
    @property
    def width_pt(self) -> float:
        return self.setup.width_pt

    @property
    def height_pt(self) -> float:
        return self.setup.height_pt

    def shows_a_grid(self, settings) -> bool:
        """Whether to rule this page. Its own answer beats the document's."""
        if self.grid is None:
            return bool(settings.show_grid)
        return self.grid

    def shows_a_header(self, settings) -> bool:
        if self.header is None:
            return bool(settings.show_header)
        return self.header

    def shows_a_footer(self, settings) -> bool:
        if self.footer is None:
            return bool(settings.show_footer)
        return self.footer

    # -- serialisation -----------------------------------------------------
    def to_dict(self) -> dict:
        items = self._pending_items
        if self.frame is not None:
            items = self.frame.serialize_items()
        return {
            "uid": self.uid,
            "label": self.label,
            "setup": self.setup.to_dict(),
            "scale": self.scale.to_dict(),
            "background_key": self.background_key,
            "background_opacity": self.background_opacity,
            "source_note": self.source_note,
            "grid": self.grid,
            "header": self.header,
            "footer": self.footer,
            "items": items,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Page":
        page = cls(PageSetup.from_dict(data.get("setup", {})), data.get("label", ""))
        page.uid = data.get("uid", page.uid)
        page.scale = PageScale.from_dict(data.get("scale", {}))
        page.background_key = data.get("background_key")
        page.background_opacity = float(data.get("background_opacity", 1.0))
        page.source_note = data.get("source_note", "")
        for which in ("grid", "header", "footer"):
            said = data.get(which)
            setattr(page, which, None if said is None else bool(said))
        page._pending_items = data.get("items", [])
        return page


@dataclass
class DocumentSettings:
    """Document-wide preferences."""

    precision: int = 4
    number_format: str = "auto"
    show_grid: bool = False
    snap_to_grid: bool = False
    # Pick up the corners, centres and ends of what is already drawn.
    snap_to_items: bool = True
    # Snapping to the drawing that came in on a PDF page, rather than to the
    # markups drawn on top of it. Kept apart because they want different
    # things: a corner of a beam is worth catching exactly, and the alignment
    # guides that help when laying markups out only get in the way over a
    # drawing that is already full of lines.
    snap_to_content: bool = True
    # Lining a markup up with the ones already drawn — level with this, in
    # line with that. Only for what has been drawn here, never for the PDF.
    snap_to_alignment: bool = True
    grid_mm: float = 5.0
    show_margins: bool = True
    math_font: str = "Cambria Math"
    math_size: float = 10.0
    header_left: str = ""
    header_center: str = ""
    header_right: str = ""
    footer_left: str = "{title}"
    footer_center: str = ""
    footer_right: str = "Page {page} of {pages}"
    show_header: bool = False
    show_footer: bool = True
    # A logo sits in one of the six header/footer slots; text in the same slot
    # steps aside for it.
    logo_key: str = ""
    logo_slot: str = "header_left"
    logo_height_mm: float = 10.0
    default_author: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentSettings":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


class Document:
    """A CalcForge project: pages, assets, settings and the shared workspace."""

    VERSION = 1

    def __init__(self):
        self.title = "Untitled"
        self.author = ""
        self.subject = ""
        self.project = ""
        self.settings = DocumentSettings()
        self.pages: list[Page] = [Page()]
        self.layers: list[Layer] = [Layer("Markups"), Layer("Calculations")]
        self.bookmarks: list[Bookmark] = []
        self.assets: dict[str, bytes] = {}
        self.workspace = Workspace()
        self.path: Optional[str] = None
        self.modified = False

    # -- pages -------------------------------------------------------------
    def add_page(self, index: Optional[int] = None, setup: Optional[PageSetup] = None) -> Page:
        template = setup or PageSetup.from_dict(self.pages[-1].setup.to_dict()) if self.pages else PageSetup()
        page = Page(template)
        if index is None:
            self.pages.append(page)
        else:
            self.pages.insert(index, page)
        self.modified = True
        return page

    def remove_page(self, index: int) -> Optional[Page]:
        if len(self.pages) <= 1 or not 0 <= index < len(self.pages):
            return None
        self.modified = True
        return self.pages.pop(index)

    def move_page(self, source: int, target: int) -> None:
        if source == target or not 0 <= source < len(self.pages):
            return
        page = self.pages.pop(source)
        self.pages.insert(max(0, min(target, len(self.pages))), page)
        self.modified = True

    def move_pages(self, source: int, count: int, target: int) -> int:
        """Move a run of *count* pages so it starts at *target*.

        A block of sheets picked out together is dragged as a block, and
        arrives in the order it left in whichever way it is going. Says the
        row the run actually starts at afterwards.
        """
        count = max(int(count), 1)
        if not 0 <= source < len(self.pages):
            return source
        moving = self.pages[source:source + count]
        if not moving or (source == target and count == 1):
            return source
        for page in moving:
            self.pages.remove(page)
        landing = max(0, min(int(target), len(self.pages)))
        for offset, page in enumerate(moving):
            self.pages.insert(landing + offset, page)
        self.modified = True
        return landing

    # -- layers ------------------------------------------------------------
    def layer(self, name: str) -> Layer:
        for layer in self.layers:
            if layer.name == name:
                return layer
        return Layer(name or "Markups")

    def layer_names(self) -> list[str]:
        return [layer.name for layer in self.layers]

    def add_layer(self, name: str) -> Layer:
        existing = set(self.layer_names())
        candidate = name or "Layer"
        index = 2
        while candidate in existing:
            candidate = f"{name} {index}"
            index += 1
        layer = Layer(candidate)
        self.layers.append(layer)
        self.modified = True
        return layer

    def index_of(self, page: Page) -> int:
        try:
            return self.pages.index(page)
        except ValueError:
            return -1

    # -- assets ------------------------------------------------------------
    def add_asset(self, data: bytes, suffix: str = "png") -> str:
        key = f"asset_{uuid.uuid4().hex[:12]}.{suffix}"
        self.assets[key] = data
        self.modified = True
        return key

    def asset(self, key: Optional[str]) -> Optional[bytes]:
        return self.assets.get(key) if key else None

    def put_asset(self, key: str, data: bytes) -> str:
        """Store an image under a key it already has.

        Pasting a snapshot into another document brings its images along, and
        they have to keep the keys the pasted items refer to.
        """
        if key and data:
            self.assets[key] = data
            self.modified = True
        return key

    def prune_assets(self, used: set[str]) -> None:
        for key in list(self.assets):
            if key not in used:
                del self.assets[key]

    # -- serialisation -----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "version": self.VERSION,
            "title": self.title,
            "author": self.author,
            "subject": self.subject,
            "project": self.project,
            "settings": self.settings.to_dict(),
            "layers": [asdict(layer) for layer in self.layers],
            "bookmarks": [mark.to_dict() for mark in self.bookmarks],
            "pages": [page.to_dict() for page in self.pages],
        }

    def load_dict(self, data: dict) -> None:
        self.title = data.get("title", "Untitled")
        self.author = data.get("author", "")
        self.subject = data.get("subject", "")
        self.project = data.get("project", "")
        self.settings = DocumentSettings.from_dict(data.get("settings", {}))
        self.layers = [Layer(**layer) for layer in data.get("layers", [])] or [Layer("Markups")]
        self.bookmarks = [Bookmark.from_dict(mark) for mark in data.get("bookmarks", [])]
        self.pages = [Page.from_dict(page) for page in data.get("pages", [])] or [Page()]
        self.modified = False

    # -- bookmarks ---------------------------------------------------------
    def page_index_of(self, uid: str) -> int:
        """Which page a bookmark points at now, or -1 if it has gone."""
        for index, page in enumerate(self.pages):
            if page.uid == uid:
                return index
        return -1

    def contents_entries(self) -> list:
        """Bookmarks that still point somewhere, in page order.

        What the bookmarks panel lists, what a contents block prints and what
        the exported PDF gets as its outline all read from here, so the three
        can never disagree.
        """
        entries = []
        for mark in self.bookmarks:
            index = self.page_index_of(mark.page_uid)
            if index >= 0:
                entries.append((mark, index))
        entries.sort(key=lambda pair: (pair[1], pair[0].y))
        return entries

    def add_bookmark(self, title: str, page_index: int, y: float = 0.0,
                     level: int = 0) -> Optional[Bookmark]:
        if not (0 <= page_index < len(self.pages)):
            return None
        mark = Bookmark(title.strip() or f"Page {page_index + 1}",
                        self.pages[page_index].uid, float(y), int(level))
        self.bookmarks.append(mark)
        self.modified = True
        return mark

    def field_values(self, page_index: int) -> dict[str, str]:
        """Values available to header/footer templates."""
        from datetime import datetime

        return {
            "title": self.title,
            "author": self.author,
            "subject": self.subject,
            "project": self.project,
            "page": str(page_index + 1),
            "pages": str(len(self.pages)),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M"),
            "file": self.path or "",
        }

    def expand_fields(self, template: str, page_index: int) -> str:
        text = template or ""
        for key, value in self.field_values(page_index).items():
            text = text.replace("{" + key + "}", value)
        return text
