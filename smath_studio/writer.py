"""Writer to serialize a Worksheet back to .sm XML format."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from .parser import (
    Assembly,
    AreaRegion,
    MathDescription,
    MathRegion,
    Metadata,
    PageModel,
    PictureRegion,
    PlotRegion,
    Region,
    Settings,
    TextContent,
    TextParagraph,
    Worksheet,
)

SM_NS = "http://smath.info/schemas/worksheet/1.0"


def write_file(worksheet: Worksheet, path: str | Path):
    """Serialize a Worksheet to a .sm XML file."""
    path = Path(path)

    lines = []
    lines.append('<?xml version="1.0" encoding="utf-8" standalone="yes"?>')

    if worksheet.app_progid:
        lines.append(f'<?application progid="{worksheet.app_progid}" version="{worksheet.app_version}"?>')

    lines.append(f'<regions xmlns="{SM_NS}">')

    # Settings
    _write_settings(lines, worksheet.settings)

    # Regions
    for region in worksheet.regions:
        _write_region(lines, region, indent=2)

    lines.append("</regions>")

    path.write_text("\n".join(lines), encoding="utf-8")


def _write_settings(lines: list[str], settings: Settings):
    dpi_attr = f' dpi="{settings.dpi}"' if settings.dpi != 96 else ""
    lines.append(f"  <settings{dpi_attr}>")

    # Identity
    lines.append("    <identity>")
    lines.append(f"      <id>{_esc(settings.identity.id)}</id>")
    lines.append(f"      <revision>{settings.identity.revision}</revision>")
    lines.append("    </identity>")

    # Metadata
    for md in settings.metadata:
        lines.append(f'    <metadata lang="{_esc(md.lang)}">')
        if md.title:
            lines.append(f"      <title>{_esc(md.title)}</title>")
        if md.author:
            lines.append(f"      <author>{_esc(md.author)}</author>")
        if md.translator:
            lines.append(f"      <translator>{_esc(md.translator)}</translator>")
        if md.description:
            lines.append(f"      <description>{_esc(md.description)}</description>")
        if md.company:
            lines.append(f"      <company>{_esc(md.company)}</company>")
        if md.keywords:
            lines.append(f"      <keywords>{_esc(md.keywords)}</keywords>")
        lines.append("    </metadata>")

    # Calculation
    calc = settings.calculation
    lines.append("    <calculation>")
    lines.append(f"      <precision>{calc.precision}</precision>")
    lines.append(f"      <exponentialThreshold>{calc.exponential_threshold}</exponentialThreshold>")
    lines.append(f"      <fractions>{calc.fractions}</fractions>")
    lines.append("    </calculation>")

    # Page model
    pm = settings.page_model
    lines.append(f'    <pageModel active="{_bool(pm.active)}">')
    lines.append(f'      <paper orientation="{pm.paper_orientation}" width="{pm.paper_width}" height="{pm.paper_height}" />')
    lines.append(f'      <margins left="{pm.margin_left}" right="{pm.margin_right}" top="{pm.margin_top}" bottom="{pm.margin_bottom}" />')
    lines.append("    </pageModel>")

    # Dependencies
    if settings.dependencies:
        lines.append("    <dependencies>")
        for dep in settings.dependencies:
            lines.append(f'      <assembly name="{_esc(dep.name)}" version="{_esc(dep.version)}" guid="{_esc(dep.guid)}" />')
        lines.append("    </dependencies>")

    lines.append("  </settings>")


def _write_region(lines: list[str], region: Region, indent: int = 2):
    pad = " " * indent
    attrs = [f'id="{region.id}"']
    if region.left is not None:
        attrs.append(f'left="{region.left}"')
    if region.top is not None:
        attrs.append(f'top="{region.top}"')
    if region.width:
        attrs.append(f'width="{region.width}"')
    if region.height:
        attrs.append(f'height="{region.height}"')
    attrs.append(f'color="{region.color}"')
    attrs.append(f'bgColor="{region.bg_color}"')
    if region.font_size != 10:
        attrs.append(f'fontSize="{region.font_size}"')
    if region.border:
        attrs.append('border="true"')
    if region.show_input_data is not None and not region.show_input_data:
        attrs.append('showInputData="False"')

    lines.append(f'{pad}<region {" ".join(attrs)}>')

    # Text
    for tc in region.text_contents:
        lines.append(f'{pad}  <text lang="{tc.lang}">')
        for p in tc.paragraphs:
            p_attrs = ""
            if p.bold:
                p_attrs += ' bold="true"'
            if p.italic:
                p_attrs += ' italic="true"'
            if p.href:
                p_attrs += f' href="{_esc(p.href)}"'
            lines.append(f"{pad}    <p{p_attrs}>{_esc(p.text)}</p>")
        lines.append(f"{pad}  </text>")

    # Math
    if region.math is not None:
        _write_math(lines, region.math, indent + 2)

    # Plot
    if region.plot is not None:
        _write_plot(lines, region.plot, indent + 2)

    # Area
    if region.area is not None:
        if region.area.is_terminator:
            lines.append(f'{pad}  <area terminator="true" />')
        elif region.area.collapsed:
            lines.append(f'{pad}  <area collapsed="true" />')
        else:
            lines.append(f"{pad}  <area />")

    # Picture
    if region.picture is not None:
        lines.append(f"{pad}  <picture>")
        lines.append(f'{pad}    <raw format="{region.picture.format}" encoding="{region.picture.encoding}">{region.picture.data}</raw>')
        lines.append(f"{pad}  </picture>")

    # Children
    for child in region.children:
        _write_region(lines, child, indent + 2)

    lines.append(f"{pad}</region>")


def _write_math(lines: list[str], math: MathRegion, indent: int):
    pad = " " * indent
    attrs = ""
    if math.optimize:
        attrs += f' optimize="{math.optimize}"'
    if math.decimal_places is not None:
        attrs += f' decimalPlaces="{math.decimal_places}"'
    if math.significant_digits_mode is not None:
        attrs += f' significantDigitsMode="{_bool(math.significant_digits_mode)}"'
    if math.trailing_zeros is not None:
        attrs += f' trailingZeros="{_bool(math.trailing_zeros)}"'

    lines.append(f"{pad}<math{attrs}>")

    # Descriptions
    for desc in math.descriptions:
        lines.append(f'{pad}  <description active="{_bool(desc.active)}" position="{desc.position}" lang="{desc.lang}">')
        lines.append(f"{pad}    <p>{_esc(desc.text)}</p>")
        lines.append(f"{pad}  </description>")

    # Input
    if math.input_elements:
        lines.append(f"{pad}  <input>")
        for e in math.input_elements:
            _write_e_element(lines, e, indent + 4)
        lines.append(f"{pad}  </input>")

    # Contract
    if math.contract_elements:
        lines.append(f"{pad}  <contract>")
        for e in math.contract_elements:
            _write_e_element(lines, e, indent + 4)
        lines.append(f"{pad}  </contract>")

    # Result
    if math.result_elements:
        lines.append(f'{pad}  <result action="{math.result_action}">')
        for e in math.result_elements:
            _write_e_element(lines, e, indent + 4)
        lines.append(f"{pad}  </result>")

    lines.append(f"{pad}</math>")


def _write_plot(lines: list[str], plot: PlotRegion, indent: int):
    pad = " " * indent
    attrs_str = " ".join(f'{k}="{v}"' for k, v in plot.attributes.items())
    lines.append(f"{pad}<plot {attrs_str}>")

    if plot.input_elements:
        lines.append(f"{pad}  <input>")
        for e in plot.input_elements:
            _write_e_element(lines, e, indent + 4)
        lines.append(f"{pad}  </input>")

    lines.append(f"{pad}</plot>")


def _write_e_element(lines: list[str], elem: ET.Element, indent: int):
    """Write a single <e> element."""
    pad = " " * indent
    # Strip namespace from tag
    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

    attrs = []
    for k, v in elem.attrib.items():
        attrs.append(f'{k}="{_esc(v)}"')

    text = elem.text or ""
    if text:
        text = _esc(text)

    if attrs:
        lines.append(f'{pad}<{tag} {" ".join(attrs)}>{text}</{tag}>')
    else:
        lines.append(f"{pad}<{tag}>{text}</{tag}>")


def _esc(text: str) -> str:
    """XML-escape text."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _bool(val: bool) -> str:
    return "true" if val else "false"
