"""Document and page model.

A document holds pages; each page holds regions (items).
Evaluation order is top-left to bottom-right across all pages.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

from PySide6.QtCore import QRectF, QPointF, QSizeF


class PageSize(Enum):
    A4 = ("A4", 595.0, 842.0)
    A3 = ("A3", 842.0, 1191.0)
    A2 = ("A2", 1191.0, 1684.0)
    A1 = ("A1", 1684.0, 2384.0)
    A0 = ("A0", 2384.0, 3370.0)
    A5 = ("A5", 420.0, 595.0)
    LETTER = ("Letter", 612.0, 792.0)
    LEGAL = ("Legal", 612.0, 1008.0)
    TABLOID = ("Tabloid", 792.0, 1224.0)

    def __init__(self, label: str, width: float, height: float):
        self._label = label
        self._width = width
        self._height = height

    @property
    def width(self) -> float:
        return self._width

    @property
    def height(self) -> float:
        return self._height

    @property
    def label(self) -> str:
        return self._label


class Orientation(Enum):
    PORTRAIT = auto()
    LANDSCAPE = auto()


@dataclass
class PageMargins:
    left: float = 56.7
    right: float = 56.7
    top: float = 56.7
    bottom: float = 56.7


@dataclass
class PageSettings:
    size: PageSize = PageSize.A4
    orientation: Orientation = Orientation.PORTRAIT
    margins: PageMargins = field(default_factory=PageMargins)
    scale: float = 1.0
    grid_visible: bool = False
    grid_snap: bool = True
    grid_spacing: float = 14.17

    @property
    def width(self) -> float:
        if self.orientation == Orientation.LANDSCAPE:
            return self.size.height
        return self.size.width

    @property
    def height(self) -> float:
        if self.orientation == Orientation.LANDSCAPE:
            return self.size.width
        return self.size.height

    @property
    def content_rect(self) -> QRectF:
        return QRectF(
            self.margins.left, self.margins.top,
            self.width - self.margins.left - self.margins.right,
            self.height - self.margins.top - self.margins.bottom,
        )


@dataclass
class Region:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = "unknown"
    x: float = 0.0
    y: float = 0.0
    width: float = 100.0
    height: float = 30.0
    page_index: int = 0
    data: dict[str, Any] = field(default_factory=dict)
    locked: bool = False
    layer: str = "default"
    visible: bool = True

    @property
    def rect(self) -> QRectF:
        return QRectF(self.x, self.y, self.width, self.height)

    @rect.setter
    def rect(self, r: QRectF):
        self.x = r.x()
        self.y = r.y()
        self.width = r.width()
        self.height = r.height()

    @property
    def sort_key(self) -> tuple[int, float, float]:
        return (self.page_index, self.y, self.x)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "page_index": self.page_index,
            "data": self.data,
            "locked": self.locked,
            "layer": self.layer,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Region":
        return cls(
            id=d.get("id", str(uuid.uuid4())[:8]),
            type=d.get("type", "unknown"),
            x=d.get("x", 0),
            y=d.get("y", 0),
            width=d.get("width", 100),
            height=d.get("height", 30),
            page_index=d.get("page_index", 0),
            data=d.get("data", {}),
            locked=d.get("locked", False),
            layer=d.get("layer", "default"),
        )


@dataclass
class Layer:
    name: str = "default"
    visible: bool = True
    locked: bool = False
    printable: bool = True


@dataclass
class Page:
    index: int = 0
    settings: PageSettings = field(default_factory=PageSettings)
    regions: list[Region] = field(default_factory=list)
    background_image: Optional[bytes] = None
    background_pdf_page: Optional[int] = None

    def add_region(self, region: Region) -> Region:
        region.page_index = self.index
        self.regions.append(region)
        return region

    def remove_region(self, region_id: str):
        self.regions = [r for r in self.regions if r.id != region_id]

    def regions_sorted(self) -> list[Region]:
        return sorted(self.regions, key=lambda r: r.sort_key)


@dataclass
class HeaderFooter:
    left: str = ""
    center: str = ""
    right: str = ""
    enabled: bool = False


@dataclass
class Document:
    title: str = "Untitled"
    author: str = ""
    project: str = ""
    pages: list[Page] = field(default_factory=list)
    layers: list[Layer] = field(default_factory=list)
    header: HeaderFooter = field(default_factory=HeaderFooter)
    footer: HeaderFooter = field(default_factory=HeaderFooter)
    modified: bool = False
    file_path: Optional[str] = None

    def __post_init__(self):
        if not self.pages:
            self.pages.append(Page(index=0))
        if not self.layers:
            self.layers.append(Layer("default"))

    def add_page(self, after_index: int = -1) -> Page:
        idx = after_index + 1 if after_index >= 0 else len(self.pages)
        page = Page(index=idx)
        if self.pages:
            page.settings = PageSettings(
                size=self.pages[0].settings.size,
                orientation=self.pages[0].settings.orientation,
                margins=PageMargins(
                    self.pages[0].settings.margins.left,
                    self.pages[0].settings.margins.right,
                    self.pages[0].settings.margins.top,
                    self.pages[0].settings.margins.bottom,
                ),
            )
        self.pages.insert(idx, page)
        self._reindex()
        self.modified = True
        return page

    def remove_page(self, index: int):
        if len(self.pages) <= 1:
            return
        del self.pages[index]
        self._reindex()
        self.modified = True

    def duplicate_page(self, index: int) -> Page:
        src = self.pages[index]
        page = self.add_page(index)
        for r in src.regions:
            d = r.to_dict()
            d["id"] = str(uuid.uuid4())[:8]
            page.add_region(Region.from_dict(d))
        return page

    def _reindex(self):
        for i, p in enumerate(self.pages):
            p.index = i
            for r in p.regions:
                r.page_index = i

    def all_regions_sorted(self) -> list[Region]:
        all_regions = []
        for page in self.pages:
            all_regions.extend(page.regions)
        return sorted(all_regions, key=lambda r: r.sort_key)

    def find_region(self, region_id: str) -> Optional[Region]:
        for page in self.pages:
            for r in page.regions:
                if r.id == region_id:
                    return r
        return None

    def to_dict(self) -> dict:
        return {
            "version": "1.0",
            "title": self.title,
            "author": self.author,
            "project": self.project,
            "pages": [
                {
                    "index": p.index,
                    "settings": {
                        "size": p.settings.size.name,
                        "orientation": p.settings.orientation.name,
                        "margins": {
                            "left": p.settings.margins.left,
                            "right": p.settings.margins.right,
                            "top": p.settings.margins.top,
                            "bottom": p.settings.margins.bottom,
                        },
                        "scale": p.settings.scale,
                        "grid_visible": p.settings.grid_visible,
                        "grid_snap": p.settings.grid_snap,
                    },
                    "regions": [r.to_dict() for r in p.regions],
                }
                for p in self.pages
            ],
            "layers": [
                {"name": l.name, "visible": l.visible,
                 "locked": l.locked, "printable": l.printable}
                for l in self.layers
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        doc = cls(
            title=d.get("title", "Untitled"),
            author=d.get("author", ""),
            project=d.get("project", ""),
        )
        doc.pages = []
        for pd in d.get("pages", []):
            ps = pd.get("settings", {})
            page = Page(
                index=pd.get("index", 0),
                settings=PageSettings(
                    size=PageSize[ps.get("size", "A4")],
                    orientation=Orientation[ps.get("orientation", "PORTRAIT")],
                    margins=PageMargins(**ps.get("margins", {})),
                    scale=ps.get("scale", 1.0),
                    grid_visible=ps.get("grid_visible", False),
                    grid_snap=ps.get("grid_snap", True),
                ),
            )
            for rd in pd.get("regions", []):
                page.add_region(Region.from_dict(rd))
            doc.pages.append(page)
        if not doc.pages:
            doc.pages.append(Page(index=0))
        for ld in d.get("layers", []):
            doc.layers.append(Layer(**ld))
        if not doc.layers:
            doc.layers.append(Layer("default"))
        return doc
