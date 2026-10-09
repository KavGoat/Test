"""Copying cells to and from Excel: its XML Spreadsheet (formulas in R1C1
form), HTML and plain text."""
from __future__ import annotations

import json

from calcforge.sheet import clip
from calcforge.sheet.workbook import Workbook

EXCEL = b'''<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:html="http://www.w3.org/TR/REC-html40">
 <Styles>
  <Style ss:ID="Default" ss:Name="Normal">
   <Alignment ss:Vertical="Bottom"/><Borders/>
   <Font ss:FontName="Calibri" x:Family="Swiss" ss:Size="11" ss:Color="#000000"/>
   <Interior/><NumberFormat/><Protection/>
  </Style>
  <Style ss:ID="s62">
   <Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="2"/></Borders>
   <Font ss:FontName="Calibri" x:Family="Swiss" ss:Size="11" ss:Color="#000000" ss:Bold="1"/>
   <Interior ss:Color="#FFFF00" ss:Pattern="Solid"/>
  </Style>
  <Style ss:ID="s63"><NumberFormat ss:Format="0.00"/></Style>
 </Styles>
 <Worksheet ss:Name="Sheet1">
  <Table ss:ExpandedColumnCount="2" ss:ExpandedRowCount="3" x:FullColumns="1" x:FullRows="1">
   <Column ss:Width="80"/>
   <Row>
    <Cell ss:StyleID="s62"><Data ss:Type="String">Load</Data></Cell>
    <Cell ss:StyleID="s62"><Data ss:Type="String">Factored</Data></Cell>
   </Row>
   <Row>
    <Cell><Data ss:Type="Number">12.5</Data></Cell>
    <Cell ss:StyleID="s63" ss:Formula="=RC[-1]*1.5"><Data ss:Type="Number">18.75</Data></Cell>
   </Row>
   <Row>
    <Cell ss:Index="2" ss:Formula="=SUM(R[-1]C:R[-1]C)"><Data ss:Type="Number">18.75</Data></Cell>
   </Row>
  </Table>
 </Worksheet>
</Workbook>'''


def test_pasting_from_excel_keeps_formulas_and_formats():
    wb = Workbook()
    s = wb.add_sheet()
    data = clip.from_clipboard({clip.MIME_EXCEL_XML: EXCEL})
    clip.paste(wb, s, 4, 2, data)              # at C5
    assert s.input(4, 2) == "Load" and s.input(5, 2) == "12.5"
    assert s.input(5, 3) == "=C6*1.5" and s.value(5, 3) == 18.75
    assert s.input(6, 3) == "=SUM(D6:D6)" and s.value(6, 3) == 18.75
    st = wb.style_of(s, 4, 2)
    assert st.bold and st.fill == "#FFFF00" and st.bottom.style == "medium"
    assert wb.style_of(s, 5, 3).number_format == "0.00"
    assert data["widths"][0] == 80


def test_copying_for_excel_writes_r1c1_formulas():
    wb = Workbook()
    s = wb.add_sheet()
    wb.set_input(s, 0, 0, "2")
    wb.set_input(s, 1, 0, "=A1*$A$1")
    wb.format_block(s, 1, 0, 1, 0, bold=True, number_format="0.0")
    out = clip.to_clipboard(s, 0, 0, 1, 0)
    xml = out[clip.MIME_EXCEL_XML].decode()
    assert 'ss:Formula="=R[-1]C*R1C1"' in xml
    assert 'ss:Bold="1"' in xml and 'ss:Format="0.0"' in xml
    assert out["text/plain"].decode() == "2\r\n4.0\r\n"
    back = clip.from_excel_xml(out[clip.MIME_EXCEL_XML])
    s2 = wb.add_sheet()
    clip.paste(wb, s2, 0, 0, back)
    assert s2.input(1, 0) == "=A1*$A$1" and s2.value(1, 0) == 4


def test_plain_text_and_html_from_other_programs():
    wb = Workbook()
    s = wb.add_sheet()
    clip.paste(wb, s, 0, 0, clip.from_text("a\t5 kN\n\"line\ttwo\"\t12%\n"))
    assert s.input(0, 1) == "5 kN" and s.input(1, 0) == "line\ttwo"
    assert wb.style_of(s, 1, 1).number_format == "0%"
    html = "<table><tr><th>Head</th><td style='background:#ff0000'>3</td></tr></table>"
    clip.paste(wb, s, 5, 0, clip.from_html(html))
    assert wb.style_of(s, 5, 0).bold and wb.style_of(s, 5, 1).fill == "#ff0000"


def test_calcforge_own_copy_round_trips_everything():
    wb = Workbook()
    s = wb.add_sheet()
    wb.set_input(s, 0, 0, "=B1+1")
    wb.set_comment(s, 0, 0, "note")
    wb.merge(s, 0, 0, 0, 1)
    data = json.loads(clip.to_clipboard(s, 0, 0, 0, 1)[clip.MIME_OWN])
    s2 = wb.add_sheet()
    clip.paste(wb, s2, 2, 2, data)
    assert s2.input(2, 2) == "=D3+1" and s2.cell(2, 2).comment == "note"
    assert s2.merges == [(2, 2, 2, 3)]
