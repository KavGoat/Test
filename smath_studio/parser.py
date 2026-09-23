"""Parser for SMath Studio .sm worksheet files (XML format)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

from .expression import ASTNode, parse_postfix


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TextParagraph:
    text: str
    bold: bool = False
    italic: bool = False
    href: Optional[str] = None
    built_in: bool = False


@dataclass
class TextContent:
    """A text element with localized paragraphs."""
    lang: str = "eng"
    paragraphs: list[TextParagraph] = field(default_factory=list)


@dataclass
class MathDescription:
    """Inline description attached to a math region."""
    text: str
    lang: str = "eng"
    position: str = "Right"
    active: bool = True


@dataclass
class MathRegion:
    """A math region containing an expression (and optionally a result)."""
    input_expr: Optional[ASTNode] = None
    output_expr: Optional[ASTNode] = None
    result_expr: Optional[ASTNode] = None
    contract_expr: Optional[ASTNode] = None  # unit conversion target
    result_action: str = "numeric"
    descriptions: list[MathDescription] = field(default_factory=list)
    # Raw elements for round-trip fidelity
    input_elements: list[ET.Element] = field(default_factory=list)
    output_elements: list[ET.Element] = field(default_factory=list)
    result_elements: list[ET.Element] = field(default_factory=list)
    contract_elements: list[ET.Element] = field(default_factory=list)
    optimize: Optional[str] = None
    decimal_places: Optional[int] = None
    significant_digits_mode: Optional[bool] = None
    trailing_zeros: Optional[bool] = None


@dataclass
class PlotRegion:
    """A plot region."""
    plot_type: str = "2d"
    input_expr: Optional[ASTNode] = None
    input_elements: list[ET.Element] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class AreaRegion:
    """A collapsible area region."""
    collapsed: bool = False
    is_terminator: bool = False


@dataclass
class PictureRegion:
    """An embedded picture."""
    format: str = "png"
    encoding: str = "base64"
    data: str = ""


@dataclass
class Region:
    """A region in the worksheet."""
    id: str = ""
    left: int = 0
    top: int = 0
    width: int = 0
    height: int = 0
    color: str = "#000000"
    bg_color: str = "#ffffff"
    font_size: int = 10
    border: bool = False
    locked: bool = False
    show_input_data: Optional[bool] = None

    # Content -- exactly one is set
    text_contents: list[TextContent] = field(default_factory=list)
    math: Optional[MathRegion] = None
    plot: Optional[PlotRegion] = None
    area: Optional[AreaRegion] = None
    picture: Optional[PictureRegion] = None

    # Nested regions (for area regions)
    children: list["Region"] = field(default_factory=list)


@dataclass
class Identity:
    id: str = ""
    revision: int = 0


@dataclass
class Metadata:
    lang: str = "eng"
    title: str = ""
    author: str = ""
    translator: str = ""
    description: str = ""
    company: str = ""
    keywords: str = ""


@dataclass
class CalculationSettings:
    precision: int = 4
    exponential_threshold: int = 5
    fractions: str = "decimal"
    trailing_zeros: bool = True
    significant_digits_mode: bool = False
    rounding_mode: int = 0


@dataclass
class HeaderFooter:
    """Header or footer text for pages."""
    text: str = ""
    alignment: str = "Center"
    color: str = "#a9a9a9"


@dataclass
class PageModel:
    active: bool = False
    view_mode: int = 0
    paper_width: int = 850
    paper_height: int = 1100
    paper_orientation: str = "Portrait"
    margin_left: int = 39
    margin_right: int = 39
    margin_top: int = 39
    margin_bottom: int = 39
    header: Optional[HeaderFooter] = None
    footer: Optional[HeaderFooter] = None


@dataclass
class Assembly:
    name: str = ""
    version: str = ""
    guid: str = ""


@dataclass
class Settings:
    dpi: int = 96
    identity: Identity = field(default_factory=Identity)
    metadata: list[Metadata] = field(default_factory=list)
    calculation: CalculationSettings = field(default_factory=CalculationSettings)
    page_model: PageModel = field(default_factory=PageModel)
    dependencies: list[Assembly] = field(default_factory=list)


@dataclass
class Worksheet:
    """A complete SMath Studio worksheet."""
    settings: Settings = field(default_factory=Settings)
    regions: list[Region] = field(default_factory=list)
    app_version: str = ""
    app_progid: str = ""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

SM_NS = "http://smath.info/schemas/worksheet/1.0"


def parse_file(path: str | Path) -> Worksheet:
    """Parse a .sm file into a Worksheet object."""
    path = Path(path)
    tree = ET.parse(path)
    root = tree.getroot()

    ns = _detect_ns(root)
    ws = Worksheet()

    # Parse processing instruction from raw XML
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        header = f.read(500)
    pi_match = re.search(r'<\?application\s+progid="([^"]*?)"\s+version="([^"]*?)"', header)
    if pi_match:
        ws.app_progid = pi_match.group(1)
        ws.app_version = pi_match.group(2)

    # Parse settings
    settings_elem = root.find(f"{ns}settings")
    if settings_elem is not None:
        ws.settings = _parse_settings(settings_elem, ns)

    # Parse regions -- the root element might be <regions> directly
    # or regions might be nested under it
    tag_local = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if tag_local == "regions":
        regions_container = root
    else:
        regions_elem = root.find(f"{ns}regions")
        regions_container = regions_elem if regions_elem is not None else root

    for region_elem in regions_container.findall(f"{ns}region"):
        region = _parse_region(region_elem, ns)
        ws.regions.append(region)

    return ws


def _detect_ns(root: ET.Element) -> str:
    m = re.match(r"\{(.+?)\}", root.tag)
    if m:
        return "{" + m.group(1) + "}"
    return ""


def _parse_settings(elem: ET.Element, ns: str) -> Settings:
    s = Settings()
    s.dpi = int(elem.get("dpi", "96") or "96")

    # Identity
    identity_elem = elem.find(f"{ns}identity")
    if identity_elem is not None:
        id_elem = identity_elem.find(f"{ns}id")
        rev_elem = identity_elem.find(f"{ns}revision")
        s.identity.id = id_elem.text if id_elem is not None and id_elem.text else ""
        s.identity.revision = int(rev_elem.text) if rev_elem is not None and rev_elem.text else 0

    # Metadata (multiple languages)
    for meta_elem in elem.findall(f"{ns}metadata"):
        md = Metadata()
        md.lang = meta_elem.get("lang", "eng")
        for child_tag in ("title", "author", "translator", "description", "company", "keywords"):
            child = meta_elem.find(f"{ns}{child_tag}")
            if child is not None and child.text:
                setattr(md, child_tag, child.text)
        s.metadata.append(md)

    # Calculation
    calc_elem = elem.find(f"{ns}calculation")
    if calc_elem is not None:
        _set_int(calc_elem, ns, "precision", s.calculation, "precision")
        _set_int(calc_elem, ns, "exponentialThreshold", s.calculation, "exponential_threshold")
        frac = calc_elem.find(f"{ns}fractions")
        if frac is not None and frac.text:
            s.calculation.fractions = frac.text
        tz = calc_elem.find(f"{ns}trailingZeros")
        if tz is not None and tz.text:
            s.calculation.trailing_zeros = tz.text.lower() == "true"
        sdm = calc_elem.find(f"{ns}significantDigitsMode")
        if sdm is not None and sdm.text:
            s.calculation.significant_digits_mode = sdm.text.lower() == "true"
        rm = calc_elem.find(f"{ns}roundingMode")
        if rm is not None and rm.text:
            s.calculation.rounding_mode = int(rm.text)

    # Page model
    pm_elem = elem.find(f"{ns}pageModel")
    if pm_elem is not None:
        s.page_model.active = pm_elem.get("active", "false").lower() == "true"
        s.page_model.view_mode = int(pm_elem.get("viewMode", "0") or "0")
        paper = pm_elem.find(f"{ns}paper")
        if paper is not None:
            s.page_model.paper_width = int(paper.get("width", "850") or "850")
            s.page_model.paper_height = int(paper.get("height", "1100") or "1100")
            s.page_model.paper_orientation = paper.get("orientation", "Portrait")
        margins = pm_elem.find(f"{ns}margins")
        if margins is not None:
            s.page_model.margin_left = int(margins.get("left", "39") or "39")
            s.page_model.margin_right = int(margins.get("right", "39") or "39")
            s.page_model.margin_top = int(margins.get("top", "39") or "39")
            s.page_model.margin_bottom = int(margins.get("bottom", "39") or "39")
        hdr = pm_elem.find(f"{ns}header")
        if hdr is not None and hdr.text:
            s.page_model.header = HeaderFooter(
                text=hdr.text,
                alignment=hdr.get("alignment", "Center"),
                color=hdr.get("color", "#a9a9a9"),
            )
        ftr = pm_elem.find(f"{ns}footer")
        if ftr is not None and ftr.text:
            s.page_model.footer = HeaderFooter(
                text=ftr.text,
                alignment=ftr.get("alignment", "Center"),
                color=ftr.get("color", "#a9a9a9"),
            )

    # Dependencies (both spellings: dependencies and dependences)
    for dep_tag in (f"{ns}dependencies", f"{ns}dependences"):
        dep_elem = elem.find(dep_tag)
        if dep_elem is not None:
            for asm in dep_elem.findall(f"{ns}assembly"):
                s.dependencies.append(Assembly(
                    name=asm.get("name", ""),
                    version=asm.get("version", ""),
                    guid=asm.get("guid", ""),
                ))

    return s


def _set_int(parent: ET.Element, ns: str, child_tag: str, obj: Any, attr: str):
    child = parent.find(f"{ns}{child_tag}")
    if child is not None and child.text:
        try:
            setattr(obj, attr, int(child.text))
        except ValueError:
            pass


def _parse_region(elem: ET.Element, ns: str) -> Region:
    """Parse a <region> element."""
    region = Region()
    region.id = elem.get("id", "")
    region.left = int(elem.get("left", "0") or "0")
    region.top = int(elem.get("top", "0") or "0")
    region.width = int(elem.get("width", "0") or "0")
    region.height = int(elem.get("height", "0") or "0")
    region.color = elem.get("color", "#000000")
    region.bg_color = elem.get("bgColor") or elem.get("background-color", "#ffffff")
    region.font_size = int((elem.get("fontSize") or elem.get("font-size", "10")) or "10")
    region.border = elem.get("border", "false").lower() == "true"
    region.locked = elem.get("isLocked", "false").lower() == "true"
    sid = elem.get("showInputData")
    if sid is not None:
        region.show_input_data = sid.lower() != "false"

    # Text content
    for text_elem in elem.findall(f"{ns}text"):
        tc = TextContent(lang=text_elem.get("lang", "eng"))
        for p_elem in text_elem.findall(f"{ns}p"):
            tp = TextParagraph(
                text=p_elem.text or "",
                bold=p_elem.get("bold", "false").lower() == "true",
                italic=p_elem.get("italic", "false").lower() == "true",
                href=p_elem.get("href"),
                built_in=p_elem.get("build-in", "false").lower() == "true",
            )
            tc.paragraphs.append(tp)
        region.text_contents.append(tc)

    # Math content
    math_elem = elem.find(f"{ns}math")
    if math_elem is not None:
        region.math = _parse_math(math_elem, ns)

    # Plot content
    plot_elem = elem.find(f"{ns}plot")
    if plot_elem is not None:
        region.plot = _parse_plot(plot_elem, ns)

    # Area content
    area_elem = elem.find(f"{ns}area")
    if area_elem is not None:
        collapsed = (area_elem.get("collapsed", "false").lower() == "true"
                     or area_elem.get("is-collapsed", "false").lower() == "true")
        region.area = AreaRegion(
            collapsed=collapsed,
            is_terminator=area_elem.get("terminator", "false").lower() == "true",
        )

    # Picture content
    picture_elem = elem.find(f"{ns}picture")
    if picture_elem is not None:
        raw = picture_elem.find(f"{ns}raw")
        if raw is not None:
            region.picture = PictureRegion(
                format=raw.get("format", "png"),
                encoding=raw.get("encoding", "base64"),
                data=raw.text or "",
            )

    # Nested regions (children of area regions)
    for child_elem in elem.findall(f"{ns}region"):
        region.children.append(_parse_region(child_elem, ns))

    return region


def _parse_math(elem: ET.Element, ns: str) -> MathRegion:
    """Parse a <math> element.

    Handles two XML layouts:
    1. Wrapped: <math><input><e>...</e></input><result>...</result></math>
    2. Flat:    <math><e>...</e><e>...</e></math>  (older/simpler files)
    """
    math = MathRegion()
    math.optimize = elem.get("optimize")

    dp = elem.get("decimalPlaces")
    if dp is not None:
        try:
            math.decimal_places = int(dp)
        except ValueError:
            pass

    sdm = elem.get("significantDigitsMode")
    if sdm is not None:
        math.significant_digits_mode = sdm.lower() == "true"

    tz = elem.get("trailingZeros")
    if tz is not None:
        math.trailing_zeros = tz.lower() == "true"

    # Descriptions
    for desc_elem in elem.findall(f"{ns}description"):
        md = MathDescription(
            text="",
            lang=desc_elem.get("lang", "eng"),
            position=desc_elem.get("position", "Right"),
            active=desc_elem.get("active", "true").lower() == "true",
        )
        p = desc_elem.find(f"{ns}p")
        if p is not None:
            md.text = p.text or ""
        math.descriptions.append(md)

    # Detect format: check for <input> wrapper vs flat <e> children
    input_elem = elem.find(f"{ns}input")
    has_wrapped = input_elem is not None

    if has_wrapped:
        # Wrapped format: <e> elements inside <input>, <output>, etc.
        e_elements = list(input_elem.findall(f"{ns}e"))
        math.input_elements = e_elements
        math.input_expr = parse_postfix(e_elements, ns)

        output_elem = elem.find(f"{ns}output")
        if output_elem is not None:
            e_elements = list(output_elem.findall(f"{ns}e"))
            math.output_elements = e_elements
            math.output_expr = parse_postfix(e_elements, ns)

        contract_elem = elem.find(f"{ns}contract")
        if contract_elem is not None:
            e_elements = list(contract_elem.findall(f"{ns}e"))
            math.contract_elements = e_elements
            math.contract_expr = parse_postfix(e_elements, ns)

        result_elem = elem.find(f"{ns}result")
        if result_elem is not None:
            math.result_action = result_elem.get("action", "numeric")
            e_elements = list(result_elem.findall(f"{ns}e"))
            math.result_elements = e_elements
            math.result_expr = parse_postfix(e_elements, ns)
    else:
        # Flat format: <e> elements directly under <math>
        e_tag = f"{ns}e" if ns else "e"
        all_e = [c for c in elem if c.tag == e_tag]
        if all_e:
            math.input_elements = all_e
            math.input_expr = parse_postfix(all_e, ns)

            # In flat format, check if the expression ends with "=" operator
            # which means it has a result display
            last_e = all_e[-1]
            if last_e.get("type") == "operator" and (last_e.text or "").strip() == "=":
                math.result_elements = all_e
                math.result_expr = math.input_expr

    return math


def _parse_plot(elem: ET.Element, ns: str) -> PlotRegion:
    """Parse a <plot> element."""
    plot = PlotRegion()
    plot.plot_type = elem.get("type", "2d")
    plot.attributes = dict(elem.attrib)

    input_elem = elem.find(f"{ns}input")
    if input_elem is not None:
        e_elements = list(input_elem.findall(f"{ns}e"))
        plot.input_elements = e_elements
        plot.input_expr = parse_postfix(e_elements, ns)

    return plot
