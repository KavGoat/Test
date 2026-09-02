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
    margin_left: float = 15.0
    margin_top: float = 15.0
    margin_right: float = 15.0
    margin_bottom: float = 15.0

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
        self.frame = None                           # set by the UI layer
        self._pending_items: list[dict] = []

    # -- geometry ----------------------------------------------------------
    @property
    def width_pt(self) -> float:
        return self.setup.width_pt

    @property
    def height_pt(self) -> float:
        return self.setup.height_pt

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
            "pages": [page.to_dict() for page in self.pages],
        }

    def load_dict(self, data: dict) -> None:
        self.title = data.get("title", "Untitled")
        self.author = data.get("author", "")
        self.subject = data.get("subject", "")
        self.project = data.get("project", "")
        self.settings = DocumentSettings.from_dict(data.get("settings", {}))
        self.layers = [Layer(**layer) for layer in data.get("layers", [])] or [Layer("Markups")]
        self.pages = [Page.from_dict(page) for page in data.get("pages", [])] or [Page()]
        self.modified = False

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
